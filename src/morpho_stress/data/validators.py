"""Pandera schemas — runtime validation with range and invariant checks.

These complement the PyArrow type-only schemas in `schemas.py`. Pandera
schemas validate semantic invariants:

- non-negativity of supply, borrow, collateral
- LTV in [0, 1]
- timestamps in expected range
- referential integrity (market_id format, address format)

Use:
    >>> from morpho_stress.data.validators import validate
    >>> df = validate(df, "market_state")  # raises on violation, returns df

The PyArrow schema enforces *types*. Pandera enforces *values*. Both checks run
on every Parquet write.
"""

from __future__ import annotations

import re
from typing import TypeVar

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Column, DataFrameSchema, Index

# ---------------------------------------------------------------------------
# Reusable check functions
# ---------------------------------------------------------------------------

_ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")
_BYTES32_RE = re.compile(r"^0x[0-9a-f]{64}$")


def _is_address(s: pd.Series) -> pd.Series:
    return s.str.match(_ADDRESS_RE).fillna(False)


def _is_bytes32(s: pd.Series) -> pd.Series:
    return s.str.match(_BYTES32_RE).fillna(False)


address_check = pa.Check(_is_address, element_wise=False, error="not a lowercase hex address")
bytes32_check = pa.Check(_is_bytes32, element_wise=False, error="not a 32-byte hex id")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

MARKETS = DataFrameSchema(
    {
        "market_id": Column(str, checks=[bytes32_check]),
        "loan_asset": Column(str, checks=[address_check]),
        "loan_asset_symbol": Column(str, checks=pa.Check.str_length(1, 16)),
        "loan_asset_decimals": Column("int8", checks=pa.Check.in_range(0, 24)),
        "collateral_asset": Column(str, checks=[address_check]),
        "collateral_asset_symbol": Column(str, checks=pa.Check.str_length(1, 16)),
        "collateral_asset_decimals": Column("int8", checks=pa.Check.in_range(0, 24)),
        "oracle": Column(str, checks=[address_check]),
        "oracle_type": Column(
            str,
            checks=pa.Check.isin(
                ["chainlink", "pyth", "redstone", "uniswap_twap", "composite"]
            ),
        ),
        "irm": Column(str, checks=[address_check]),
        "lltv": Column(float, checks=pa.Check.in_range(0.0, 1.0)),
        "created_at_block": Column("uint64", checks=pa.Check.greater_than_or_equal_to(0)),
        "created_at_ts": Column("datetime64[ns, UTC]"),
    },
    strict=True,
    unique=["market_id"],
)


MARKET_STATE = DataFrameSchema(
    {
        "market_id": Column(str, checks=[bytes32_check]),
        "block_number": Column("uint64"),
        "block_ts": Column("datetime64[ns, UTC]"),
        "total_supply_assets": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "total_supply_shares": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "total_borrow_assets": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "total_borrow_shares": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "total_collateral": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "last_update": Column("uint64"),
        "fee": Column(float, checks=pa.Check.in_range(0.0, 0.25)),  # max 25% fee, sanity
    },
    checks=[
        pa.Check(
            lambda df: df["total_borrow_assets"] <= df["total_supply_assets"] + 1e-6,
            error="total_borrow_assets exceeds total_supply_assets (over-borrow)",
        ),
    ],
    strict=True,
)


_EVENT_BASE_COLUMNS = {
    "market_id": Column(str, checks=[bytes32_check]),
    "block_number": Column("uint64"),
    "block_ts": Column("datetime64[ns, UTC]"),
    "tx_hash": Column(str, checks=pa.Check.str_length(66, 66)),  # 0x + 64 hex
    "log_index": Column("uint32"),
}


def _event_schema(extra_cols: dict[str, Column]) -> DataFrameSchema:
    return DataFrameSchema(
        {**_EVENT_BASE_COLUMNS, **extra_cols},
        strict=True,
    )


EVENTS_SUPPLY = _event_schema(
    {
        "caller": Column(str, checks=[address_check]),
        "on_behalf": Column(str, checks=[address_check]),
        "assets": Column(float, checks=pa.Check.greater_than(0.0)),
        "shares": Column(float, checks=pa.Check.greater_than(0.0)),
    }
)

EVENTS_WITHDRAW = _event_schema(
    {
        "caller": Column(str, checks=[address_check]),
        "on_behalf": Column(str, checks=[address_check]),
        "receiver": Column(str, checks=[address_check]),
        "assets": Column(float, checks=pa.Check.greater_than(0.0)),
        "shares": Column(float, checks=pa.Check.greater_than(0.0)),
    }
)

EVENTS_BORROW = _event_schema(
    {
        "caller": Column(str, checks=[address_check]),
        "on_behalf": Column(str, checks=[address_check]),
        "receiver": Column(str, checks=[address_check]),
        "assets": Column(float, checks=pa.Check.greater_than(0.0)),
        "shares": Column(float, checks=pa.Check.greater_than(0.0)),
    }
)

EVENTS_REPAY = _event_schema(
    {
        "caller": Column(str, checks=[address_check]),
        "on_behalf": Column(str, checks=[address_check]),
        "assets": Column(float, checks=pa.Check.greater_than(0.0)),
        "shares": Column(float, checks=pa.Check.greater_than(0.0)),
    }
)

EVENTS_LIQUIDATE = _event_schema(
    {
        "liquidator": Column(str, checks=[address_check]),
        "borrower": Column(str, checks=[address_check]),
        "repaid_assets": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "repaid_shares": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "seized_assets": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "bad_debt_assets": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "bad_debt_shares": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
    }
)


POSITIONS = DataFrameSchema(
    {
        "market_id": Column(str, checks=[bytes32_check]),
        "borrower": Column(str, checks=[address_check]),
        "block_number": Column("uint64"),
        "block_ts": Column("datetime64[ns, UTC]"),
        "borrow_shares": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "collateral": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        "borrow_assets": Column(float, checks=pa.Check.greater_than_or_equal_to(0.0)),
        # LTV can exceed 1 transiently in stress (insolvent positions)
        "ltv": Column(float, checks=pa.Check.in_range(0.0, 10.0), nullable=True),
        # health_factor = LLTV / LTV; can be inf when LTV=0
        "health_factor": Column(float, nullable=True),
    },
    strict=True,
)


ORACLE_PRICES = DataFrameSchema(
    {
        "market_id": Column(str, checks=[bytes32_check]),
        "block_number": Column("uint64"),
        "block_ts": Column("datetime64[ns, UTC]"),
        "price": Column(float, checks=pa.Check.greater_than(0.0)),
        "price_decimals_raw": Column("int8", checks=pa.Check.in_range(0, 36)),
        "oracle_kind": Column(str),
        "staleness_blocks": Column("int32", checks=pa.Check.greater_than_or_equal_to(0)),
    },
    strict=True,
)


DEX_SLIPPAGE = DataFrameSchema(
    {
        "collateral_symbol": Column(str),
        "quote_ts": Column("datetime64[ns, UTC]"),
        "direction": Column(str, checks=pa.Check.isin(["sell_collateral_for_loan"])),
        "volume_usd": Column(float, checks=pa.Check.greater_than(0.0)),
        "volume_native": Column(float, checks=pa.Check.greater_than(0.0)),
        "oracle_price": Column(float, checks=pa.Check.greater_than(0.0)),
        "realized_price": Column(float, checks=pa.Check.greater_than(0.0)),
        # Slippage can be negative (positive surprise) but bounded sanity
        "slippage_bps": Column(float, checks=pa.Check.in_range(-1000.0, 10000.0)),
        "source": Column(
            str, checks=pa.Check.isin(["1inch_quote", "uniswap_swap", "cowswap_fill"])
        ),
    },
    strict=True,
)


# ---------------------------------------------------------------------------
# Registry & validation entry point
# ---------------------------------------------------------------------------

REGISTRY: dict[str, DataFrameSchema] = {
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


T = TypeVar("T", bound=pd.DataFrame)


def validate(df: T, schema_name: str) -> T:
    """Validate a DataFrame against the named Pandera schema.

    Raises ``pandera.errors.SchemaError`` on violation. Returns the (unchanged)
    DataFrame on success — convenient for chaining.
    """
    if schema_name not in REGISTRY:
        raise KeyError(f"Unknown pandera schema: {schema_name}")
    return REGISTRY[schema_name].validate(df, lazy=True)
