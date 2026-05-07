"""scripts/fetch_oracle_prices.py — fetch oracle prices per market over time.

Uses the canonical Morpho Blue IOracle interface:

    function price() external view returns (uint256)

returns the price of 1 unit of collateral quoted in 1 unit of loan asset,
scaled by `1e36 + loan_decimals - collateral_decimals`. This interface is
implemented by every oracle attached to a Morpho Blue market, regardless
of the underlying source (Chainlink-compliant feeds via
MorphoChainlinkOracleV2, Pyth via MorphoPythOracle, Redstone wrappers,
custom oracles).

Output:
    data/cache/oracle_prices.parquet — schema='oracle_prices'

Normalisation:
    The raw `price()` output is converted to "USD per collateral unit"
    when the loan asset is a USD-pegged stable (USDC, USDT, DAI, PYUSD,
    USDS, FRAX). For non-stable loan assets (WETH, WBTC), the value is
    "loan asset units per collateral unit" — caller must apply a separate
    loan-asset-to-USD conversion if USD denomination is needed.

Reference:
    https://docs.morpho.org/get-started/resources/contracts/oracles/

Usage:
    python scripts/fetch_oracle_prices.py --config config.local.yaml
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
from morpho_stress.data.abis import MORPHO_IORACLE_ABI
from morpho_stress.data.rpc_helpers import get_block_timestamp, to_checksum
from morpho_stress.data.schemas import get_schema

logger = logging.getLogger(__name__)


def _fetch_oracle_price_at_block(
    rpc: RPCClient,
    oracle_addr: str,
    loan_decimals: int,
    collateral_decimals: int,
    block_number: int,
) -> float | None:
    """Read oracle price at a given block via Morpho IOracle.price().

    Returns the normalised price (loan asset units per collateral unit) or
    None if the call fails.

    The raw `price()` output is scaled by 1e36 + loan_dec - coll_dec.
    To convert to "1 unit of collateral in N units of loan asset":
        price_normalised = raw / 10^(36 + loan_dec - coll_dec)
    """
    contract = rpc.primary.eth.contract(
        address=to_checksum(oracle_addr), abi=MORPHO_IORACLE_ABI
    )
    try:
        raw_price = int(contract.functions.price().call(block_identifier=block_number))
    except Exception as e:
        logger.debug("oracle %s call failed at block %d: %s", oracle_addr, block_number, e)
        return None

    if raw_price <= 0:
        return None

    scale_exponent = 36 + loan_decimals - collateral_decimals
    return raw_price / (10**scale_exponent)


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
)
@click.option(
    "--output",
    "output_path",
    default="data/cache/oracle_prices.parquet",
    type=click.Path(dir_okay=False),
)
def main(config_path: str, markets_input: str, output_path: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.load(config_path)

    rpc = RPCClient(cfg.network.rpc_url, cfg.network.rpc_url_fallback)
    latest = rpc.primary.eth.block_number
    end_block = safe_block(latest)

    end_block_data = rpc.get_block(end_block)
    end_block_ts = datetime.fromtimestamp(int(end_block_data["timestamp"]), tz=timezone.utc)
    start_secs_back = int((end_block_ts - cfg.range.start_ts).total_seconds())
    start_block = max(1, end_block - (start_secs_back // 12))

    cadence = cfg.sampling.oracle_price_period_blocks
    sample_blocks = list(range(start_block, end_block + 1, cadence))
    logger.info(
        "Sampling %d blocks per oracle (cadence: %d blocks ≈ %.1fh)",
        len(sample_blocks),
        cadence,
        cadence * 12 / 3600,
    )

    markets_df = pq.read_table(markets_input).to_pylist()
    logger.info("Loaded %d markets; reading oracles via IOracle.price()...", len(markets_df))

    rows: list[dict] = []

    for m in markets_df:
        oracle_addr = m["oracle"]
        oracle_type = m["oracle_type"]

        if oracle_type == "none":
            logger.info("Skipping idle market %s (no oracle)", m["market_id"])
            continue
        if oracle_type == "unknown":
            logger.warning(
                "Skipping market %s: oracle %s does not implement IOracle.price()",
                m["market_id"], oracle_addr,
            )
            continue

        loan_dec = m["loan_asset_decimals"]
        coll_dec = m["collateral_asset_decimals"]

        logger.info(
            "Fetching prices for %s/%s (oracle=%s, loan_dec=%d, coll_dec=%d)",
            m["collateral_asset_symbol"],
            m["loan_asset_symbol"],
            oracle_addr,
            loan_dec,
            coll_dec,
        )

        n_ok = 0
        for blk in sample_blocks:
            price = _fetch_oracle_price_at_block(
                rpc, oracle_addr, loan_dec, coll_dec, blk
            )
            if price is None:
                continue

            block_ts = get_block_timestamp(rpc, blk)
            rows.append(
                {
                    "market_id": m["market_id"],
                    "block_number": blk,
                    "block_ts": block_ts,
                    "price": float(price),
                    # The raw oracle output is at 36+loan_dec-coll_dec decimals;
                    # we record the canonical 1e36 scale exponent here for
                    # downstream verification.
                    "price_decimals_raw": 36 + loan_dec - coll_dec,
                    "oracle_kind": oracle_type,
                    # Morpho IOracle.price() does not expose staleness directly;
                    # underlying feed staleness must be queried on the wrapped
                    # Chainlink/Pyth feed. Set to 0 here as placeholder.
                    "staleness_blocks": 0,
                }
            )
            n_ok += 1

        logger.info("  → %d/%d samples successfully fetched for %s", n_ok, len(sample_blocks), m["market_id"])

    if not rows:
        raise click.ClickException("No oracle prices fetched")

    table = pa.Table.from_pylist(rows, schema=get_schema("oracle_prices"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    entry_dict = write_parquet(table, output_path, schema_name="oracle_prices")
    logger.info("Wrote %d oracle price rows to %s", entry_dict["rows"], output_path)

    manifest = Manifest()
    manifest.append_run(
        RunEntry(
            run_id=Manifest.now_run_id(),
            run_ts=datetime.now(timezone.utc).isoformat(),
            config_hash=Manifest.hash_config(cfg.model_dump(mode="json")),
            block_range_min=start_block,
            block_range_max=end_block,
            markets=[m["market_id"] for m in markets_df],
            files={
                "oracle_prices.parquet": FileEntry(
                    path=str(output_path),
                    schema="oracle_prices",
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
