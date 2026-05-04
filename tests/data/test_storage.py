"""Tests for the storage layer — schema validation on Parquet write/read."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pytest

from morpho_stress.data import get_schema, read_parquet, write_parquet
from morpho_stress.data.schemas import REGISTRY


def _sample_markets_table() -> pa.Table:
    schema = get_schema("markets")
    data = {
        "market_id": ["0x" + "ab" * 32],
        "loan_asset": ["0x" + "11" * 20],
        "loan_asset_symbol": ["USDC"],
        "loan_asset_decimals": [6],
        "collateral_asset": ["0x" + "22" * 20],
        "collateral_asset_symbol": ["wstETH"],
        "collateral_asset_decimals": [18],
        "oracle": ["0x" + "33" * 20],
        "oracle_type": ["chainlink"],
        "irm": ["0x" + "44" * 20],
        "lltv": [0.86],
        "created_at_block": [21_000_000],
        "created_at_ts": [datetime(2024, 12, 1, tzinfo=timezone.utc)],
    }
    return pa.Table.from_pydict(data, schema=schema)


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    table = _sample_markets_table()
    out_path = tmp_path / "markets.parquet"

    entry = write_parquet(table, out_path, schema_name="markets")
    assert entry["rows"] == 1
    assert entry["bytes"] > 0
    assert len(entry["sha256"]) == 64

    rebuilt = read_parquet(out_path, schema_name="markets")
    assert rebuilt.num_rows == 1
    assert rebuilt.column("loan_asset_symbol").to_pylist() == ["USDC"]


def test_write_rejects_wrong_type(tmp_path: Path) -> None:
    table = _sample_markets_table()
    # Cast lltv to float32 — should fail validation against float64 schema.
    cols = table.column_names
    new_columns = [
        table.column(c).cast(pa.float32()) if c == "lltv" else table.column(c)
        for c in cols
    ]
    bad = pa.Table.from_arrays(new_columns, names=cols)
    with pytest.raises(ValueError, match="Schema mismatch"):
        write_parquet(bad, tmp_path / "x.parquet", schema_name="markets")


def test_write_rejects_missing_column(tmp_path: Path) -> None:
    table = _sample_markets_table()
    pruned = table.drop(["fee"]) if "fee" in table.column_names else table.drop(["lltv"])
    with pytest.raises(ValueError, match="Schema mismatch"):
        write_parquet(pruned, tmp_path / "x.parquet", schema_name="markets")


def test_write_rejects_extra_column(tmp_path: Path) -> None:
    table = _sample_markets_table()
    extra = table.append_column("rogue", pa.array(["unwanted"], type=pa.string()))
    with pytest.raises(ValueError, match="Schema mismatch"):
        write_parquet(extra, tmp_path / "x.parquet", schema_name="markets")


def test_read_validates_schema(tmp_path: Path) -> None:
    table = _sample_markets_table()
    out_path = tmp_path / "markets.parquet"
    write_parquet(table, out_path, schema_name="markets")
    # Reading with a different schema name should raise.
    with pytest.raises(ValueError, match="schema drift"):
        read_parquet(out_path, schema_name="market_state")


def test_all_registered_schemas_have_unique_field_names() -> None:
    """Sanity: every schema's columns are uniquely named."""
    for name, schema in REGISTRY.items():
        names = list(schema.names)
        assert len(names) == len(set(names)), f"duplicate columns in {name}"


def test_event_schemas_share_base_fields() -> None:
    """The 5 event schemas all share the base block + tx fields."""
    base = {"market_id", "block_number", "block_ts", "tx_hash", "log_index"}
    for name in (
        "events_supply",
        "events_withdraw",
        "events_borrow",
        "events_repay",
        "events_liquidate",
    ):
        names = set(REGISTRY[name].names)
        missing = base - names
        assert not missing, f"{name} missing base fields: {missing}"
