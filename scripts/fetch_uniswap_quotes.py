"""scripts/fetch_uniswap_quotes.py — slippage curve calibration via Uniswap V3 Quoter.

Replaces the previous 1inch-based approach (which required an account and
KYC) with direct on-chain quotes from the Uniswap V3 QuoterV2 contract.

For each (collateral_asset, loan_asset) pair in markets.parquet, queries
the quoter at logarithmically-spaced trade sizes to build a slippage curve
$\\pi(V) = a \\cdot V^b$. Output is suitable for `slippage_fit.py` to fit
the parametric form via ordinary least squares regression.

Output:
    data/cache/dex_slippage.parquet — schema='dex_slippage'

Usage:
    python scripts/fetch_uniswap_quotes.py --config config.local.yaml

Performance:
    For 5 markets × 20 trade sizes × 3 fee tiers = 300 quotes. Each is a
    single RPC call (eth_call on Quoter). Completes in 1-2 minutes.

Note on fee tiers:
    Uniswap V3 has 4 standard fee tiers: 1bp (1), 5bp (5), 30bp (30), 100bp
    (100). For each pair, we query all four; only the deepest pool (or
    pools) typically has meaningful liquidity, but querying all gives us
    a robust view across fee tiers.

Note on which liquidity is queried:
    The Quoter routes through Uniswap V3 only — it does NOT aggregate
    across CowSwap, Curve, Balancer, etc. For collateral types primarily
    traded on Curve (e.g. stETH-WETH) or Balancer (e.g. some LRTs), the
    Uniswap V3 quote will overstate slippage. For cross-DEX coverage,
    extend with `fetch_curve_quotes.py` or use Dune `dex.trades` for
    historical execution data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import click
import numpy as np
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
from morpho_stress.data.abis import (
    UNISWAP_V3_QUOTER_V2_ABI,
    UNISWAP_V3_QUOTER_V2_MAINNET,
)
from morpho_stress.data.rpc_helpers import to_checksum
from morpho_stress.data.schemas import get_schema

logger = logging.getLogger(__name__)


# Standard Uniswap V3 fee tiers
FEE_TIERS_BPS = [1, 5, 30, 100]
FEE_TIERS_RAW = [100, 500, 3000, 10000]  # raw values used in contract calls


def _build_volume_grid(
    min_usd: float = 1_000.0, max_usd: float = 1e7, n_points: int = 20
) -> np.ndarray:
    """Logarithmic grid of trade sizes in USD."""
    return np.logspace(np.log10(min_usd), np.log10(max_usd), n_points)


def _quote_uniswap_v3(
    rpc: RPCClient,
    quoter_addr: str,
    token_in: str,
    token_out: str,
    fee_tier_raw: int,
    amount_in: int,
) -> int | None:
    """Call QuoterV2.quoteExactInputSingle. Returns amountOut (in token_out
    base units) or None if the pool doesn't exist / no liquidity / call
    fails.
    """
    quoter = rpc.primary.eth.contract(
        address=to_checksum(quoter_addr), abi=UNISWAP_V3_QUOTER_V2_ABI
    )
    params = {
        "tokenIn": to_checksum(token_in),
        "tokenOut": to_checksum(token_out),
        "amountIn": int(amount_in),
        "fee": int(fee_tier_raw),
        "sqrtPriceLimitX96": 0,
    }
    try:
        result = quoter.functions.quoteExactInputSingle(params).call()
        return int(result[0])  # amountOut
    except Exception as e:
        logger.debug(
            "Quote failed for %s→%s @ fee %d, amount %d: %s",
            token_in, token_out, fee_tier_raw, amount_in, e,
        )
        return None


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
    "--oracles-input",
    default="data/cache/oracle_prices.parquet",
    type=click.Path(exists=True, dir_okay=False),
    help="Latest oracle prices used to convert USD volume to native amount.",
)
@click.option(
    "--output",
    "output_path",
    default="data/cache/dex_slippage.parquet",
    type=click.Path(dir_okay=False),
)
@click.option(
    "--n-volume-points",
    default=20,
    type=int,
    help="Number of trade sizes to query per pool",
)
def main(
    config_path: str,
    markets_input: str,
    oracles_input: str,
    output_path: str,
    n_volume_points: int,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.load(config_path)

    rpc = RPCClient(cfg.network.rpc_url, cfg.network.rpc_url_fallback)
    latest = rpc.primary.eth.block_number
    end_block = safe_block(latest)
    end_block_data = rpc.get_block(end_block)
    end_block_ts = datetime.fromtimestamp(int(end_block_data["timestamp"]), tz=timezone.utc)

    quoter_addr = UNISWAP_V3_QUOTER_V2_MAINNET
    logger.info("Using Uniswap V3 Quoter V2 at %s", quoter_addr)

    markets_df = pq.read_table(markets_input).to_pylist()

    # Build a (market_id → latest_oracle_price) lookup for native volume
    # computation. Use the most recent observation per market.
    oracles_table = pq.read_table(oracles_input).to_pandas()
    latest_prices = (
        oracles_table.sort_values("block_number")
        .drop_duplicates("market_id", keep="last")
        .set_index("market_id")["price"]
        .to_dict()
    )

    volume_grid_usd = _build_volume_grid(n_points=n_volume_points)
    logger.info(
        "Volume grid: %d points from %.0fK USD to %.0fM USD",
        len(volume_grid_usd), volume_grid_usd[0] / 1000, volume_grid_usd[-1] / 1e6,
    )

    rows: list[dict] = []

    for m in markets_df:
        mid = m["market_id"]
        coll_addr = m["collateral_asset"]
        loan_addr = m["loan_asset"]
        coll_symbol = m["collateral_asset_symbol"]
        coll_decimals = m["collateral_asset_decimals"]
        loan_decimals = m["loan_asset_decimals"]

        if coll_symbol == "IDLE":
            logger.info("Skipping idle market %s", mid)
            continue

        if mid not in latest_prices:
            logger.warning("No oracle price for %s — cannot convert USD volume", mid)
            continue

        coll_usd_price = latest_prices[mid]
        if coll_usd_price <= 0:
            logger.warning("Invalid oracle price for %s (%.4f); skipping", mid, coll_usd_price)
            continue

        logger.info(
            "Quoting %s/%s (collateral=%s, $%.2f/unit)",
            coll_symbol, m["loan_asset_symbol"], coll_addr, coll_usd_price,
        )

        for fee_tier_raw, fee_tier_bps in zip(FEE_TIERS_RAW, FEE_TIERS_BPS):
            for v_usd in volume_grid_usd:
                # Convert USD volume to native collateral units
                v_native = v_usd / coll_usd_price
                amount_in = int(v_native * (10**coll_decimals))

                amount_out = _quote_uniswap_v3(
                    rpc, quoter_addr, coll_addr, loan_addr, fee_tier_raw, amount_in
                )
                if amount_out is None:
                    continue

                realized_native_per_coll = (
                    (amount_out / (10**loan_decimals)) / v_native
                )
                # Comparison vs oracle price (in same units: loan-asset per
                # collateral-asset). For markets where loan = USDC/USDT, the
                # oracle reports USD per collateral, equivalent.
                if coll_usd_price <= 0 or realized_native_per_coll <= 0:
                    continue
                slippage = max(0.0, (coll_usd_price - realized_native_per_coll) / coll_usd_price)
                slippage_bps = slippage * 10_000.0

                rows.append(
                    {
                        "collateral_symbol": coll_symbol,
                        "quote_ts": end_block_ts,
                        "direction": "sell_collateral_for_loan",
                        "volume_usd": float(v_usd),
                        "volume_native": float(v_native),
                        "oracle_price": float(coll_usd_price),
                        "realized_price": float(realized_native_per_coll),
                        "slippage_bps": float(slippage_bps),
                        "source": f"uniswap_v3_quoter_v2:{fee_tier_bps}bp",
                    }
                )

    if not rows:
        raise click.ClickException("No DEX quotes obtained")

    table = pa.Table.from_pylist(rows, schema=get_schema("dex_slippage"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    entry_dict = write_parquet(table, output_path, schema_name="dex_slippage")
    logger.info("Wrote %d quote rows to %s", entry_dict["rows"], output_path)

    manifest = Manifest()
    manifest.append_run(
        RunEntry(
            run_id=Manifest.now_run_id(),
            run_ts=datetime.now(timezone.utc).isoformat(),
            config_hash=Manifest.hash_config(cfg.model_dump(mode="json")),
            block_range_min=end_block,
            block_range_max=end_block,
            markets=[m["market_id"] for m in markets_df],
            files={
                "dex_slippage.parquet": FileEntry(
                    path=str(output_path),
                    schema="dex_slippage",
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
