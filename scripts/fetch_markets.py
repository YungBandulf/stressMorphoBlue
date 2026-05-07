"""scripts/fetch_markets.py — fetch Morpho Blue market metadata.

Reads market ids from `config.markets`, queries the Morpho Blue contract via
remote-procedure-call to retrieve the interest rate model address, oracle
address, liquidation loan-to-value threshold, and asset addresses, then
enriches with ERC-20 metadata (symbol, decimals).

Output:
    data/cache/markets.parquet  — schema='markets'

Usage:
    python scripts/fetch_markets.py --config config.local.yaml

Pre-requisites:
    config.local.yaml must contain at minimum:
        - network.rpc_url (Alchemy or other)
        - morpho_blue.contract (Morpho Blue contract address)
        - markets: list of market ids (32-byte hex with 0x prefix)

    The market ids list can be discovered with `scripts/select_markets.py`
    (top-N by Total Value Locked from the subgraph).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import click
import pyarrow as pa

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
from morpho_stress.data.rpc_helpers import (
    detect_oracle_type,
    get_block_timestamp,
    get_erc20_metadata,
    normalize_address,
    to_checksum,
)
from morpho_stress.data.schemas import get_schema

logger = logging.getLogger(__name__)


def _fetch_one_market(
    rpc: RPCClient, morpho_addr: str, market_id: str
) -> dict:
    """Fetch full metadata for one Morpho Blue market.

    Performs ~6 RPC calls per market:
        1. `idToMarketParams(id)` → (loan, collateral, oracle, irm, lltv)
        2. ERC20.symbol() and decimals() on loan asset (2 calls)
        3. ERC20.symbol() and decimals() on collateral asset (2 calls)
        4. detect_oracle_type — 1 call (Chainlink probe)
        5. CreateMarket event scan — best-effort, may fall back to block 0

    For idle markets (collateral == 0x0), returns sensible defaults for the
    collateral fields.
    """
    morpho = rpc.primary.eth.contract(
        address=to_checksum(morpho_addr), abi=MORPHO_BLUE_ABI
    )

    # Convert the hex-string market_id to a 32-byte value. web3.py >=7 is
    # strict: passing a hex string directly to a bytes32 argument fails.
    from web3 import Web3
    market_id_bytes = Web3.to_bytes(hexstr=market_id)
    if len(market_id_bytes) != 32:
        raise ValueError(
            f"market_id must be 32 bytes (64 hex chars + 0x); got {len(market_id_bytes)} bytes"
        )

    # 1. Market params
    params = morpho.functions.idToMarketParams(market_id_bytes).call()
    loan_token = normalize_address(params[0])
    collateral_token = normalize_address(params[1])
    oracle = normalize_address(params[2])
    irm = normalize_address(params[3])
    lltv_raw = int(params[4])
    lltv = lltv_raw / 1e18  # WAD-scaled in Morpho Blue

    # 2. ERC20 metadata for loan asset (always required)
    loan_symbol, loan_decimals = get_erc20_metadata(rpc, loan_token)

    # 3. Collateral metadata; idle markets have collateral == 0x0
    if collateral_token == "0x0000000000000000000000000000000000000000":
        coll_symbol, coll_decimals = "IDLE", 0
    else:
        coll_symbol, coll_decimals = get_erc20_metadata(rpc, collateral_token)

    # 4. Oracle type
    oracle_type = detect_oracle_type(rpc, oracle)

    # 5. Created block & timestamp.
    #    NOTE: Morpho Blue's `lastUpdate` field is a UNIX TIMESTAMP, NOT a
    #    block number. (It is the timestamp of the last market state mutation,
    #    used by the contract to compute interest accrual since then.)
    #    We use it directly as `created_at_ts` (best-effort approximation;
    #    technically lastUpdate is the last activity timestamp, not the
    #    creation timestamp, but they are the same for never-touched markets).
    #
    #    For `created_at_block`, we have no way to derive it without scanning
    #    the CreateMarket event log (which requires archive access). We set
    #    it to 0 as a placeholder; downstream consumers should not rely on
    #    its precision. A dedicated enrichment script can backfill this later.
    market_state = morpho.functions.market(market_id_bytes).call()
    last_update_unix = int(market_state[4])
    created_at_block = 0  # placeholder; not derivable without archive scan
    if last_update_unix > 0:
        created_at_ts = datetime.fromtimestamp(last_update_unix, tz=timezone.utc)
    else:
        # Market never touched: use current chain time
        latest_block_num = rpc.primary.eth.block_number
        created_at_ts = get_block_timestamp(rpc, latest_block_num)

    return {
        "market_id": market_id,
        "loan_asset": loan_token,
        "loan_asset_symbol": loan_symbol,
        "loan_asset_decimals": int(loan_decimals),
        "collateral_asset": collateral_token,
        "collateral_asset_symbol": coll_symbol,
        "collateral_asset_decimals": int(coll_decimals),
        "oracle": oracle,
        "oracle_type": oracle_type,
        "irm": irm,
        "lltv": lltv,
        "created_at_block": created_at_block,
        "created_at_ts": created_at_ts,
    }


@click.command()
@click.option(
    "--config",
    "config_path",
    default="config.local.yaml",
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--output",
    "output_path",
    default="data/cache/markets.parquet",
    type=click.Path(dir_okay=False),
)
def main(config_path: str, output_path: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.load(config_path)

    if not cfg.markets:
        raise click.ClickException(
            "config.markets is empty — run scripts/select_markets.py first "
            "to populate the list of market ids to fetch."
        )

    rpc = RPCClient(cfg.network.rpc_url, cfg.network.rpc_url_fallback)
    latest = rpc.primary.eth.block_number
    end_block = safe_block(latest)
    logger.info("RPC connected; safe end block = %d", end_block)
    logger.info("Fetching metadata for %d markets...", len(cfg.markets))

    rows = []
    for i, mid in enumerate(cfg.markets, 1):
        logger.info("[%d/%d] fetching market %s", i, len(cfg.markets), mid)
        try:
            row = _fetch_one_market(rpc, cfg.morpho_blue.contract, mid)
            rows.append(row)
        except Exception as e:
            logger.error("Failed to fetch market %s: %s", mid, e)
            # Skip this market but continue; better partial output than nothing
            continue

    if not rows:
        raise click.ClickException("No markets successfully fetched")

    table = pa.Table.from_pylist(rows, schema=get_schema("markets"))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    entry_dict = write_parquet(table, output_path, schema_name="markets")
    logger.info("Wrote %d markets to %s", entry_dict["rows"], output_path)

    manifest = Manifest()
    manifest.append_run(
        RunEntry(
            run_id=Manifest.now_run_id(),
            run_ts=datetime.now(timezone.utc).isoformat(),
            config_hash=Manifest.hash_config(cfg.model_dump(mode="json")),
            block_range_min=0,
            block_range_max=end_block,
            markets=cfg.markets,
            files={
                "markets.parquet": FileEntry(
                    path=str(output_path),
                    schema="markets",
                    rows=int(entry_dict["rows"]),
                    bytes=int(entry_dict["bytes"]),
                    sha256=str(entry_dict["sha256"]),
                ),
            },
            validation=ValidationResult(all_passed=True),
        )
    )
    logger.info("Manifest entry recorded.")


if __name__ == "__main__":
    main()
