"""scripts/select_markets.py — discover top-N Morpho Blue markets by Total Supply.

Queries the Morpho official GraphQL API at api.morpho.org/graphql, which is
the canonical source for Morpho protocol data (no API key required, public).

Output:
    markets_top.yaml — to be appended/merged into config.local.yaml manually,
        OR with --in-place to patch config.local.yaml directly.

Usage:
    python scripts/select_markets.py --top 10 --in-place

Note on the API endpoint:
    The official Morpho GraphQL API is at https://api.morpho.org/graphql.
    No authentication required, public, free, maintained by Morpho Labs.

    The Graph hosted subgraph at api.thegraph.com/subgraphs/name/morpho-org/...
    has been deprecated as of late 2024 (returns 301 → error.thegraph.com).

    For applications needing The Graph network, see Morpho docs:
    https://docs.morpho.org/tools/offchain/subgraphs/
"""

from __future__ import annotations

import logging
from pathlib import Path

import click
import yaml

from morpho_stress.config import Config
from morpho_stress.data.subgraph import SubgraphClient

logger = logging.getLogger(__name__)


# Morpho API native schema query.
# - Result is wrapped in `markets { items: [...] }` (not directly an array).
# - Filter: listed=true (curated) and chainId=1 (Ethereum mainnet).
# - Order by SupplyAssetsUsd descending = ranking by USD-denominated TVL.
# Reference: https://docs.morpho.org/tools/offchain/api/morpho/
TOP_MARKETS_QUERY = """
query TopMarkets($first: Int!) {
  markets(
    first: $first
    orderBy: SupplyAssetsUsd
    orderDirection: Desc
    where: {chainId_in: [1], whitelisted: true}
  ) {
    items {
      uniqueKey
      lltv
      oracleAddress
      irmAddress
      loanAsset { address symbol decimals }
      collateralAsset { address symbol decimals }
      state {
        supplyAssets
        supplyAssetsUsd
        borrowAssets
        borrowAssetsUsd
        utilization
      }
    }
  }
}
"""


def _format_market_summary(m: dict) -> str:
    coll = m.get("collateralAsset") or {"symbol": "IDLE"}
    loan = m.get("loanAsset") or {"symbol": "?"}
    state = m.get("state") or {}
    supply_usd = float(state.get("supplyAssetsUsd") or 0) / 1e6
    util = float(state.get("utilization") or 0) * 100
    return (
        f"{coll.get('symbol', '?')}/{loan.get('symbol', '?')}: "
        f"supply≈${supply_usd:.1f}M, utilization={util:.1f}%"
    )


@click.command()
@click.option(
    "--config",
    "config_path",
    default="config.local.yaml",
    type=click.Path(exists=True, dir_okay=False),
)
@click.option("--top", "top_n", default=10, type=int, help="Number of markets to select")
@click.option(
    "--output",
    "output_path",
    default="markets_top.yaml",
    type=click.Path(dir_okay=False),
    help="Output YAML snippet (NOT the full config; just markets list)",
)
@click.option(
    "--in-place",
    is_flag=True,
    help="If set, also patch config.local.yaml to include the discovered markets",
)
def main(config_path: str, top_n: int, output_path: str, in_place: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.load(config_path)

    if not cfg.subgraph or not cfg.subgraph.url:
        raise click.ClickException(
            "config.subgraph.url is required. For the Morpho native API:\n"
            "  subgraph:\n"
            '    url: "https://api.morpho.org/graphql"\n'
            "    api_key: null  # not required for the public Morpho API"
        )

    logger.info("Querying Morpho API for top-%d markets by SupplyAssetsUsd...", top_n)

    with SubgraphClient(cfg.subgraph.url, cfg.subgraph.api_key) as client:
        result = client._post(TOP_MARKETS_QUERY, {"first": top_n})

    markets_wrapper = result.get("markets", {})
    markets = markets_wrapper.get("items", [])

    if not markets:
        raise click.ClickException(
            "Morpho API returned no markets. Possible causes: API endpoint "
            "down, schema changed, or filter too restrictive. Check at "
            "https://api.morpho.org/graphql in a browser."
        )

    # Filter: keep only markets with non-null collateral (skip idle markets)
    active_markets = [m for m in markets if m.get("collateralAsset") is not None]

    logger.info("Found %d markets (%d active):", len(markets), len(active_markets))
    for i, m in enumerate(active_markets, 1):
        logger.info("  [%d] id=%s — %s", i, m.get("uniqueKey", "?"), _format_market_summary(m))

    if not active_markets:
        raise click.ClickException("No active markets (with collateral) found")

    market_ids = [m["uniqueKey"] for m in active_markets]

    # Write standalone YAML snippet
    output = Path(output_path)
    output.write_text(yaml.safe_dump({"markets": market_ids}, sort_keys=False))
    logger.info("Wrote %d market ids to %s", len(market_ids), output)

    if in_place:
        cfg_path = Path(config_path)
        with cfg_path.open() as f:
            raw_cfg = yaml.safe_load(f)
        raw_cfg["markets"] = market_ids
        with cfg_path.open("w") as f:
            yaml.safe_dump(raw_cfg, f, sort_keys=False)
        logger.info("Patched %s in place with %d market ids", cfg_path, len(market_ids))


if __name__ == "__main__":
    main()
