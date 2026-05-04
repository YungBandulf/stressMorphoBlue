"""Strict PyArrow schemas for all Parquet outputs.

Each schema is the contract between Phase 2 (data acquisition) and Phase 3
(modeling). Type drift = test failure. New columns are additive only with
explicit version bump.
"""

from __future__ import annotations

import pyarrow as pa

# ---------------------------------------------------------------------------
# Common type aliases
# ---------------------------------------------------------------------------

ADDRESS = pa.string()  # lowercase 0x-prefixed Ethereum address
BYTES32 = pa.string()  # 0x + 64 hex chars (Morpho market id)
TS_UTC = pa.timestamp("ns", tz="UTC")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

MARKETS = pa.schema(
    [
        ("market_id", BYTES32),
        ("loan_asset", ADDRESS),
        ("loan_asset_symbol", pa.string()),
        ("loan_asset_decimals", pa.int8()),
        ("collateral_asset", ADDRESS),
        ("collateral_asset_symbol", pa.string()),
        ("collateral_asset_decimals", pa.int8()),
        ("oracle", ADDRESS),
        ("oracle_type", pa.string()),  # categorical
        ("irm", ADDRESS),
        ("lltv", pa.float64()),
        ("created_at_block", pa.uint64()),
        ("created_at_ts", TS_UTC),
    ]
)


MARKET_STATE = pa.schema(
    [
        ("market_id", BYTES32),
        ("block_number", pa.uint64()),
        ("block_ts", TS_UTC),
        ("total_supply_assets", pa.float64()),
        ("total_supply_shares", pa.float64()),
        ("total_borrow_assets", pa.float64()),
        ("total_borrow_shares", pa.float64()),
        ("total_collateral", pa.float64()),
        ("last_update", pa.uint64()),
        ("fee", pa.float64()),
    ]
)


_EVENT_BASE_FIELDS = [
    ("market_id", BYTES32),
    ("block_number", pa.uint64()),
    ("block_ts", TS_UTC),
    ("tx_hash", pa.string()),
    ("log_index", pa.uint32()),
]


EVENTS_SUPPLY = pa.schema(
    _EVENT_BASE_FIELDS
    + [
        ("caller", ADDRESS),
        ("on_behalf", ADDRESS),
        ("assets", pa.float64()),
        ("shares", pa.float64()),
    ]
)


EVENTS_WITHDRAW = pa.schema(
    _EVENT_BASE_FIELDS
    + [
        ("caller", ADDRESS),
        ("on_behalf", ADDRESS),
        ("receiver", ADDRESS),
        ("assets", pa.float64()),
        ("shares", pa.float64()),
    ]
)


EVENTS_BORROW = pa.schema(
    _EVENT_BASE_FIELDS
    + [
        ("caller", ADDRESS),
        ("on_behalf", ADDRESS),
        ("receiver", ADDRESS),
        ("assets", pa.float64()),
        ("shares", pa.float64()),
    ]
)


EVENTS_REPAY = pa.schema(
    _EVENT_BASE_FIELDS
    + [
        ("caller", ADDRESS),
        ("on_behalf", ADDRESS),
        ("assets", pa.float64()),
        ("shares", pa.float64()),
    ]
)


EVENTS_LIQUIDATE = pa.schema(
    _EVENT_BASE_FIELDS
    + [
        ("liquidator", ADDRESS),
        ("borrower", ADDRESS),
        ("repaid_assets", pa.float64()),
        ("repaid_shares", pa.float64()),
        ("seized_assets", pa.float64()),
        ("bad_debt_assets", pa.float64()),
        ("bad_debt_shares", pa.float64()),
    ]
)


POSITIONS = pa.schema(
    [
        ("market_id", BYTES32),
        ("borrower", ADDRESS),
        ("block_number", pa.uint64()),
        ("block_ts", TS_UTC),
        ("borrow_shares", pa.float64()),
        ("collateral", pa.float64()),
        ("borrow_assets", pa.float64()),
        ("ltv", pa.float64()),
        ("health_factor", pa.float64()),
    ]
)


ORACLE_PRICES = pa.schema(
    [
        ("market_id", BYTES32),
        ("block_number", pa.uint64()),
        ("block_ts", TS_UTC),
        ("price", pa.float64()),
        ("price_decimals_raw", pa.int8()),
        ("oracle_kind", pa.string()),
        ("staleness_blocks", pa.int32()),
    ]
)


DEX_SLIPPAGE = pa.schema(
    [
        ("collateral_symbol", pa.string()),
        ("quote_ts", TS_UTC),
        ("direction", pa.string()),
        ("volume_usd", pa.float64()),
        ("volume_native", pa.float64()),
        ("oracle_price", pa.float64()),
        ("realized_price", pa.float64()),
        ("slippage_bps", pa.float64()),
        ("source", pa.string()),
    ]
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, pa.Schema] = {
    "markets": MARKETS,
    "market_state": MARKET_STATE,
    "events_supply": EVENTS_SUPPLY,
    "events_withdraw": EVENTS_WITHDRAW,
    "events_borrow": EVENTS_BORROW,
    "events_repay": EVENTS_REPAY,
    "events_liquidate": EVENTS_LIQUIDATE,
    "positions": POSITIONS,
    "oracle_prices": ORACLE_PRICES,
    "dex_slippage": DEX_SLIPPAGE,
}


def get_schema(name: str) -> pa.Schema:
    """Return the canonical schema for a given table name."""
    if name not in REGISTRY:
        raise KeyError(f"Unknown schema: {name}. Known: {sorted(REGISTRY)}")
    return REGISTRY[name]
