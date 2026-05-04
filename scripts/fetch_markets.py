"""scripts/fetch_markets.py — fetch Morpho Blue market metadata.

Reads market ids from config.markets, queries the Morpho Blue contract via RPC
to retrieve the IRM, oracle, LLTV, and asset addresses, then enriches with
ERC-20 metadata (symbol, decimals).

Outputs:
    data/cache/markets.parquet  — schema=markets

Usage:
    python scripts/fetch_markets.py --config config.local.yaml

Status: SKELETON — Phase 2 implementation pending. The orchestration is
correct; ABI loading and RPC calls are stubbed and clearly marked.
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
from morpho_stress.data.schemas import get_schema

logger = logging.getLogger(__name__)


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
            "config.markets is empty — run scripts/select_markets.py first"
        )

    rpc = RPCClient(cfg.network.rpc_url, cfg.network.rpc_url_fallback)
    latest = rpc.primary.eth.block_number
    end_block = safe_block(latest)
    logger.info("RPC connected; safe end block = %d", end_block)

    rows = [_fetch_one_market(rpc, cfg.morpho_blue.contract, mid) for mid in cfg.markets]
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


def _fetch_one_market(rpc: RPCClient, morpho_addr: str, market_id: str) -> dict:
    """Fetch market params for one Morpho Blue market.

    NOTE: stub. Phase 2 implementation will:
      1. Load Morpho Blue ABI from src/morpho_stress/abi/morpho.json
      2. Build contract = rpc.primary.eth.contract(address=morpho_addr, abi=...)
      3. Call contract.functions.idToMarketParams(market_id).call()
      4. Read CreateMarket event for created_at_block / created_at_ts
      5. For each asset: call ERC20.symbol() and ERC20.decimals() via RPC
      6. Detect oracle_type by inspecting the oracle contract code/interface
    """
    raise NotImplementedError(
        "fetch_one_market is stubbed; implement Morpho Blue ABI calls in Phase 2"
    )


if __name__ == "__main__":
    main()
