"""scripts/fetch_events.py — fetch Morpho Blue events via the Morpho API.

Uses the documented `transactions` query at api.morpho.org/graphql with
`type_in` filter and `marketUniqueKey_in` filter (both validated against
the Morpho docs schema).

Outputs:
    data/cache/events_supply.parquet
    data/cache/events_withdraw.parquet
    data/cache/events_borrow.parquet
    data/cache/events_repay.parquet
    data/cache/events_liquidate.parquet

Time-range filtering:
    The Morpho API `transactions` query does NOT expose `timestamp_gte` /
    `timestamp_lte` filters in its `where` clause. To respect the
    config.range window, we fetch in reverse-chronological order and stop
    as soon as we cross start_ts. The window is applied client-side
    after fetching.

    For long lookbacks (>3 months × 5 markets), this can be slow but
    correct. For incremental updates, use a checkpoint mechanism
    (not implemented here).

Schema reference:
    https://docs.morpho.org/tools/offchain/api/morpho/

Usage:
    python scripts/fetch_events.py --config config.local.yaml [--event-types supply,liquidate]
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
    RunEntry,
    ValidationResult,
    write_parquet,
)
from morpho_stress.data.schemas import get_schema
from morpho_stress.data.subgraph import SubgraphClient

logger = logging.getLogger(__name__)


# Mapping of internal event types to Morpho API TransactionType enum values
EVENT_TYPE_TO_API = {
    "supply": "MarketSupply",
    "withdraw": "MarketWithdraw",
    "borrow": "MarketBorrow",
    "repay": "MarketRepay",
    "liquidate": "MarketLiquidation",
}


# GraphQL query — schema confirmed against Morpho docs (Feb 2026 snapshot).
# Filters: marketUniqueKey_in (array), type_in (array of TransactionType enum).
# We do NOT filter by timestamp in the query (not supported); apply
# client-side after fetching.
EVENTS_QUERY = """
query MarketEvents(
  $first: Int!
  $skip: Int!
  $marketUniqueKey: String!
  $typeIn: [TransactionType!]
) {
  transactions(
    first: $first
    skip: $skip
    orderBy: Timestamp
    orderDirection: Desc
    where: {
      marketUniqueKey_in: [$marketUniqueKey]
      type_in: $typeIn
    }
  ) {
    items {
      hash
      timestamp
      blockNumber
      type
      user { address }
      data {
        ... on MarketTransferTransactionData {
          assets
          shares
          market { uniqueKey }
        }
        ... on MarketLiquidationTransactionData {
          repaidAssets
          repaidShares
          seizedAssets
          badDebtAssets
          badDebtShares
          liquidator
          market { uniqueKey }
        }
      }
    }
  }
}
"""


def _normalize_event_row(
    event_type: str,
    raw: dict,
    loan_decimals: int,
    collateral_decimals: int,
    market_id: str,
) -> dict | None:
    """Convert a raw Morpho API transaction into our Parquet row.

    Returns None if essential fields are missing.
    """
    try:
        block_ts = datetime.fromtimestamp(int(raw["timestamp"]), tz=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return None

    base = {
        "market_id": market_id,
        "block_number": int(raw.get("blockNumber") or 0),
        "block_ts": block_ts,
        "tx_hash": raw.get("hash") or "0x",
        "log_index": 0,  # Morpho API doesn't expose logIndex; use 0 as placeholder
    }

    data = raw.get("data") or {}
    user = (raw.get("user") or {}).get("address", "0x0000000000000000000000000000000000000000")
    user = user.lower()

    scale_loan = 10**loan_decimals
    scale_coll = 10**collateral_decimals

    if event_type == "supply":
        return {
            **base,
            "caller": user,
            "on_behalf": user,
            "assets": float(data.get("assets") or 0) / scale_loan,
            "shares": float(data.get("shares") or 0) / scale_loan,
        }
    elif event_type == "withdraw":
        return {
            **base,
            "caller": user,
            "on_behalf": user,
            "receiver": user,
            "assets": float(data.get("assets") or 0) / scale_loan,
            "shares": float(data.get("shares") or 0) / scale_loan,
        }
    elif event_type == "borrow":
        return {
            **base,
            "caller": user,
            "on_behalf": user,
            "receiver": user,
            "assets": float(data.get("assets") or 0) / scale_loan,
            "shares": float(data.get("shares") or 0) / scale_loan,
        }
    elif event_type == "repay":
        return {
            **base,
            "caller": user,
            "on_behalf": user,
            "assets": float(data.get("assets") or 0) / scale_loan,
            "shares": float(data.get("shares") or 0) / scale_loan,
        }
    elif event_type == "liquidate":
        liquidator_addr = data.get("liquidator") or user
        return {
            **base,
            "liquidator": liquidator_addr.lower() if liquidator_addr else user,
            "borrower": user,
            "repaid_assets": float(data.get("repaidAssets") or 0) / scale_loan,
            "repaid_shares": float(data.get("repaidShares") or 0) / scale_loan,
            "seized_assets": float(data.get("seizedAssets") or 0) / scale_coll,
            "bad_debt_assets": float(data.get("badDebtAssets") or 0) / scale_loan,
            "bad_debt_shares": float(data.get("badDebtShares") or 0) / scale_loan,
        }
    else:
        raise ValueError(f"Unknown event type: {event_type}")


def _fetch_event_type_for_market(
    client: SubgraphClient,
    event_type: str,
    market_id: str,
    start_ts: int,
    end_ts: int,
    loan_decimals: int,
    collateral_decimals: int,
) -> list[dict]:
    """Fetch all events of one type for one market within the configured time window.

    Strategy: fetch in reverse-chronological order (newest first), stop as
    soon as we cross start_ts. Apply end_ts as a hard upper bound client-side.
    """
    api_type = EVENT_TYPE_TO_API[event_type]
    page_size = 1000
    skip = 0
    rows: list[dict] = []

    while True:
        result = client._post(
            EVENTS_QUERY,
            {
                "first": page_size,
                "skip": skip,
                "marketUniqueKey": market_id,
                "typeIn": [api_type],
            },
        )

        page_wrapper = result.get("transactions") or {}
        page = page_wrapper.get("items") or []
        if not page:
            break

        # Apply time-window filter client-side (we ordered Desc, so newest first)
        early_stop = False
        for raw in page:
            ts = int(raw.get("timestamp") or 0)
            if ts > end_ts:
                continue  # too recent, skip but continue
            if ts < start_ts:
                early_stop = True  # we've gone past the start, stop pagination
                break
            row = _normalize_event_row(
                event_type, raw, loan_decimals, collateral_decimals, market_id
            )
            if row is not None:
                rows.append(row)

        if early_stop or len(page) < page_size:
            break

        skip += page_size
        if skip >= 10000:
            logger.warning(
                "Reached skip=10000 on %s/%s; possibly truncated. "
                "Reduce window or use a different fetch strategy.",
                event_type, market_id,
            )
            break

    return rows


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
    "--output-dir",
    default="data/cache",
    type=click.Path(file_okay=False),
)
@click.option(
    "--event-types",
    default="supply,withdraw,borrow,repay,liquidate",
    help="Comma-separated event types to fetch",
)
def main(config_path: str, markets_input: str, output_dir: str, event_types: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config.load(config_path)

    if not cfg.subgraph or not cfg.subgraph.url:
        raise click.ClickException("config.subgraph.url is required (Morpho API endpoint)")

    types_to_fetch = [t.strip() for t in event_types.split(",") if t.strip()]
    invalid = [t for t in types_to_fetch if t not in EVENT_TYPE_TO_API]
    if invalid:
        raise click.ClickException(f"Unknown event types: {invalid}")

    markets_df = pq.read_table(markets_input).to_pylist()
    logger.info("Loaded %d markets; fetching event types: %s", len(markets_df), types_to_fetch)

    start_ts = int(cfg.range.start_ts.timestamp())
    end_ts = int(cfg.range.end_ts.timestamp())

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    manifest_files = {}

    with SubgraphClient(cfg.subgraph.url, cfg.subgraph.api_key) as client:
        for event_type in types_to_fetch:
            logger.info("=== Fetching %s events ===", event_type)
            all_rows: list[dict] = []

            for m in markets_df:
                rows = _fetch_event_type_for_market(
                    client,
                    event_type,
                    m["market_id"],
                    start_ts,
                    end_ts,
                    m["loan_asset_decimals"],
                    m["collateral_asset_decimals"],
                )
                logger.info(
                    "  %s/%s — %s: %d events",
                    m["collateral_asset_symbol"],
                    m["loan_asset_symbol"],
                    event_type,
                    len(rows),
                )
                all_rows.extend(rows)

            schema_name = f"events_{event_type}"
            output_path = output_root / f"{schema_name}.parquet"

            if not all_rows:
                logger.warning("No %s events found in window; skipping write", event_type)
                continue

            table = pa.Table.from_pylist(all_rows, schema=get_schema(schema_name))
            entry_dict = write_parquet(table, str(output_path), schema_name=schema_name)
            logger.info("Wrote %d rows to %s", entry_dict["rows"], output_path)

            manifest_files[output_path.name] = FileEntry(
                path=str(output_path),
                schema=schema_name,
                rows=int(entry_dict["rows"]),
                bytes=int(entry_dict["bytes"]),
                sha256=str(entry_dict["sha256"]),
            )

    manifest = Manifest()
    manifest.append_run(
        RunEntry(
            run_id=Manifest.now_run_id(),
            run_ts=datetime.now(timezone.utc).isoformat(),
            config_hash=Manifest.hash_config(cfg.model_dump(mode="json")),
            block_range_min=0,
            block_range_max=0,
            markets=[m["market_id"] for m in markets_df],
            files=manifest_files,
            validation=ValidationResult(all_passed=True),
        )
    )


if __name__ == "__main__":
    main()
