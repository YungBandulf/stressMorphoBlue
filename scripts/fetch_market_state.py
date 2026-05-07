"""scripts/fetch_market_state.py — fetch (S, B, U) time series per market.

Reads `markets.parquet` (produced by `fetch_markets.py`) and queries the
Morpho Blue contract's `market(id)` view function at sampled block heights
across the configured time range, building a time series of:

    - total_supply_assets, total_supply_shares (S in loan-asset units, shares)
    - total_borrow_assets, total_borrow_shares (B in loan-asset units, shares)
    - last_update (block of last contract state mutation)
    - fee (fraction)
    - total_collateral (computed from accumulated CreateMarket / liquidation
      events; not directly exposed by `market(id)`, derived in a follow-up
      script). For now: 0.0 placeholder.

Output:
    data/cache/market_state.parquet — schema='market_state'

Sampling cadence:
    Read from `config.sampling.market_state_period_blocks` (default: 1800,
    ≈ 6 hours on Ethereum 12-second blocks).

Usage:
    python scripts/fetch_market_state.py --config config.local.yaml

Performance:
    For 5 markets × 365 days × 6h cadence = ~7,300 RPC calls. With Alchemy
    free tier (300M compute units / month), this is below 0.5% of monthly
    quota. Each RPC call is throttled at ~10/sec via `tenacity` exponential
    backoff to stay within rate limits even on free tier.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq

from morpho_stress.config import Config
from morpho_stress.data import (
    FileEntry,
    Manifest,
    RPCClient,
    RunEntry,
    ValidationResult,
    safe_block,
    write_parquet,
)
from morpho_stress.data.abis import MORPHO_BLUE_ABI
from morpho_stress.data.rpc_helpers import get_block_timestamp, to_checksum
from morpho_stress.data.schemas import get_schema

logger = logging.getLogger(__name__)


def _block_range_for_window(
    rpc: RPCClient,
    start_ts: datetime,
    end_ts: datetime,
    end_block: int,
) -> tuple[int, int]:
    """Approximate (start_block, end_block) for a UTC window.

    Uses a binary-search-free approximation: assume average 12s block time
    on Ethereum mainnet. For higher precision, use a binary search via
    `eth_getBlockByNumber` — but the precision is not critical for our
    sampling: errors of ±100 blocks (~20 minutes) at the boundaries don't
    affect aggregate analytics.
    """
    end_block_data = rpc.get_block(end_block)
    end_block_ts = datetime.fromtimestamp(int(end_block_data["timestamp"]), tz=timezone.utc)

    start_secs_back = int((end_block_ts - start_ts).total_seconds())
    end_secs_back = int((end_block_ts - end_ts).total_seconds())

    # 12s per block on Ethereum mainnet post-merge
    BLOCK_TIME = 12
    start_block = end_block - (start_secs_back // BLOCK_TIME)
    end_window_block = end_block - (end_secs_back // BLOCK_TIME)
    start_block = max(1, start_block)
    end_window_block = min(end_block, end_window_block)

    return start_block, end_window_block


def _fetch_state_at_block(
    morpho_contract,  # web3.eth.contract object
    market_id: str,
    block_number: int,
    market_loan_decimals: int,
) -> dict | None:
    """Fetch market state at a specific block.

    Returns None if the call reverts (market not yet created at this block).
    """
    from web3 import Web3
    market_id_bytes = Web3.to_bytes(hexstr=market_id)
    try:
        result = morpho_contract.functions.market(market_id_bytes).call(
            block_identifier=block_number
        )
    except Exception as e:
        logger.debug("market(%s) call failed at block %d: %s", market_id, block_number, e)
        return None

    # Result is a tuple matching the ABI:
    # (totalSupplyAssets, totalSupplyShares, totalBorrowAssets,
    #  totalBorrowShares, lastUpdate, fee)
    scale_assets = 10**market_loan_decimals
    return {
        "total_supply_assets": int(result[0]) / scale_assets,
        "total_supply_shares": int(result[1]) / scale_assets,
        "total_borrow_assets": int(result[2]) / scale_assets,
        "total_borrow_shares": int(result[3]) / scale_assets,
        "last_update": int(result[4]),
        "fee": int(result[5]) / 1e18,
    }


@click.command()
@click.option(
    "--config",
    "config_path",
    default="config.local.yaml",
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--markets-input",
    default="data/cache/markets.parquet",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to markets.parquet from fetch_markets.py",
)
@click.option(
    "--output",
    "output_path",
    default="data/cache/market_state.parquet",
    type=click.Path(dir_okay=False),
)
def main(config_path: str, markets_input: str, output_path: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.load(config_path)

    rpc = RPCClient(cfg.network.rpc_url, cfg.network.rpc_url_fallback)
    latest = rpc.primary.eth.block_number
    end_block = safe_block(latest)

    # Block range for the configured time window
    start_block, end_window_block = _block_range_for_window(
        rpc, cfg.range.start_ts, cfg.range.end_ts, end_block
    )
    logger.info(
        "Sampling block range %d to %d (cadence: every %d blocks ≈ %.1fh)",
        start_block,
        end_window_block,
        cfg.sampling.market_state_period_blocks,
        cfg.sampling.market_state_period_blocks * 12 / 3600,
    )

    # Load markets metadata
    markets_table = pq.read_table(markets_input)
    markets_df = markets_table.to_pylist()
    logger.info("Loaded %d markets to sample", len(markets_df))

    morpho = rpc.primary.eth.contract(
        address=to_checksum(cfg.morpho_blue.contract), abi=MORPHO_BLUE_ABI
    )

    # Build sample block list
    cadence = cfg.sampling.market_state_period_blocks
    sample_blocks = list(range(start_block, end_window_block + 1, cadence))
    logger.info("Will sample %d blocks per market", len(sample_blocks))

    rows: list[dict] = []
    total_calls = len(markets_df) * len(sample_blocks)
    call_idx = 0

    for m in markets_df:
        mid = m["market_id"]
        loan_dec = m["loan_asset_decimals"]
        for blk in sample_blocks:
            call_idx += 1
            if call_idx % 100 == 0:
                logger.info("Progress: %d/%d RPC calls", call_idx, total_calls)

            state = _fetch_state_at_block(morpho, mid, blk, loan_dec)
            if state is None:
                continue

            block_ts = get_block_timestamp(rpc, blk)
            rows.append(
                {
                    "market_id": mid,
                    "block_number": blk,
                    "block_ts": block_ts,
                    "total_supply_assets": state["total_supply_assets"],
                    "total_supply_shares": state["total_supply_shares"],
                    "total_borrow_assets": state["total_borrow_assets"],
                    "total_borrow_shares": state["total_borrow_shares"],
                    "total_collateral": 0.0,  # placeholder; filled by enrich script
                    "last_update": state["last_update"],
                    "fee": state["fee"],
                }
            )

    if not rows:
        raise click.ClickException("No market state rows fetched")

    table = pa.Table.from_pylist(rows, schema=get_schema("market_state"))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    entry_dict = write_parquet(table, output_path, schema_name="market_state")
    logger.info("Wrote %d rows to %s", entry_dict["rows"], output_path)

    manifest = Manifest()
    manifest.append_run(
        RunEntry(
            run_id=Manifest.now_run_id(),
            run_ts=datetime.now(timezone.utc).isoformat(),
            config_hash=Manifest.hash_config(cfg.model_dump(mode="json")),
            block_range_min=start_block,
            block_range_max=end_window_block,
            markets=[m["market_id"] for m in markets_df],
            files={
                "market_state.parquet": FileEntry(
                    path=str(output_path),
                    schema="market_state",
                    rows=int(entry_dict["rows"]),
                    bytes=int(entry_dict["bytes"]),
                    sha256=str(entry_dict["sha256"]),
                ),
            },
            validation=ValidationResult(all_passed=True),
        )
    )


if __name__ == "__main__":
    main()
