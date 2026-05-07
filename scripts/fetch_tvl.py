"""scripts/fetch_tvl.py — fetch Morpho Blue Total Value Locked time series from DeFiLlama.

Pulls the daily Total Value Locked time series for the Morpho Blue
protocol from DeFiLlama's public API (no authentication required).

Output:
    data/cache/tvl_daily.parquet — schema='tvl_daily'

Usage:
    python scripts/fetch_tvl.py [--protocol morpho-blue]

Note:
    DeFiLlama's protocol slug for Morpho Blue may evolve. Verify on
    https://defillama.com/protocols/morpho if results are empty.
    Common slugs: 'morpho-blue', 'morpho', 'morphoblue'.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import click
import httpx
import pyarrow as pa

from morpho_stress.data import (
    FileEntry,
    Manifest,
    RunEntry,
    ValidationResult,
    write_parquet,
)
from morpho_stress.data.schemas import get_schema

logger = logging.getLogger(__name__)


DEFILLAMA_BASE = "https://api.llama.fi"


def _fetch_protocol_tvl(protocol_slug: str) -> dict:
    """Fetch the protocol detail JSON from DeFiLlama."""
    url = f"{DEFILLAMA_BASE}/protocol/{protocol_slug}"
    logger.info("GET %s", url)
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


def _flatten_tvl_history(payload: dict, protocol: str) -> list[dict]:
    """Convert DeFiLlama response to one row per (chain, date)."""
    rows = []
    chain_tvls = payload.get("chainTvls", {})

    for chain_name, chain_data in chain_tvls.items():
        # The chainTvls entries have shape { "tvl": [{date, totalLiquidityUSD}, ...] }
        # Skip aggregate "borrowed", "lent" sub-categories (not the main TVL)
        if "-" in chain_name:  # e.g. "Ethereum-borrowed"
            continue
        tvl_history = chain_data.get("tvl", [])
        for entry in tvl_history:
            ts = int(entry["date"])
            d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            rows.append(
                {
                    "date": d,
                    "protocol": protocol,
                    "chain": chain_name.lower(),
                    "tvl_usd": float(entry.get("totalLiquidityUSD", 0.0)),
                    "source": "defillama",
                }
            )
    return rows


@click.command()
@click.option("--protocol", default="morpho-blue", help="DeFiLlama protocol slug")
@click.option(
    "--output",
    "output_path",
    default="data/cache/tvl_daily.parquet",
    type=click.Path(dir_okay=False),
)
def main(protocol: str, output_path: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    payload = _fetch_protocol_tvl(protocol)
    rows = _flatten_tvl_history(payload, protocol)

    if not rows:
        # Try alternative slugs
        for alt in ["morpho", "morphoblue"]:
            if alt == protocol:
                continue
            logger.warning("No data for slug '%s'; trying '%s'", protocol, alt)
            try:
                payload = _fetch_protocol_tvl(alt)
                rows = _flatten_tvl_history(payload, alt)
                if rows:
                    protocol = alt
                    break
            except httpx.HTTPError:
                continue

    if not rows:
        raise click.ClickException(
            f"No TVL data found for any of: {protocol}, morpho, morphoblue"
        )

    table = pa.Table.from_pylist(rows, schema=get_schema("tvl_daily"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    entry_dict = write_parquet(table, output_path, schema_name="tvl_daily")
    logger.info("Wrote %d TVL rows for protocol '%s' to %s", entry_dict["rows"], protocol, output_path)

    manifest = Manifest()
    manifest.append_run(
        RunEntry(
            run_id=Manifest.now_run_id(),
            run_ts=datetime.now(timezone.utc).isoformat(),
            config_hash="defillama_only",
            block_range_min=0,
            block_range_max=0,
            markets=[],
            files={
                "tvl_daily.parquet": FileEntry(
                    path=str(output_path),
                    schema="tvl_daily",
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
