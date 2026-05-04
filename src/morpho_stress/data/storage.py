"""Parquet IO with strict schema validation.

All writes go through `write_parquet`, which validates the table against the
registry schema before writing. This is the only chokepoint between in-memory
DataFrames and the on-disk cache.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from morpho_stress.data.schemas import get_schema


def write_parquet(
    table: pa.Table,
    path: str | Path,
    schema_name: str,
    compression: str = "zstd",
) -> dict[str, int | str]:
    """Validate `table` against the registered schema and write to Parquet.

    Returns a manifest entry with sha256, row count, byte count.
    """
    expected = get_schema(schema_name)
    # Strict equality: same fields, same order, same types. Metadata ignored.
    if not table.schema.equals(expected, check_metadata=False):
        diff = _schema_diff(table.schema, expected)
        raise ValueError(
            f"Schema mismatch for {schema_name}:\n{diff}"
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression=compression)

    digest = _file_sha256(path)
    return {
        "path": str(path),
        "schema": schema_name,
        "rows": table.num_rows,
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def read_parquet(path: str | Path, schema_name: str | None = None) -> pa.Table:
    """Read a Parquet file, optionally re-validating schema."""
    path = Path(path)
    table = pq.read_table(path)
    if schema_name is not None:
        expected = get_schema(schema_name)
        if not table.schema.equals(expected, check_metadata=False):
            diff = _schema_diff(table.schema, expected)
            raise ValueError(f"On-disk schema drift in {path}:\n{diff}")
    return table


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _schema_diff(actual: pa.Schema, expected: pa.Schema) -> str:
    actual_fields = {f.name: f.type for f in actual}
    expected_fields = {f.name: f.type for f in expected}
    lines: list[str] = []
    missing = set(expected_fields) - set(actual_fields)
    extra = set(actual_fields) - set(expected_fields)
    common = set(actual_fields) & set(expected_fields)
    if missing:
        lines.append(f"  missing fields: {sorted(missing)}")
    if extra:
        lines.append(f"  extra fields:   {sorted(extra)}")
    for name in sorted(common):
        if actual_fields[name] != expected_fields[name]:
            lines.append(
                f"  type mismatch on '{name}': "
                f"actual={actual_fields[name]} expected={expected_fields[name]}"
            )
    # Field order matters for our equality check
    if list(actual.names) != list(expected.names) and not lines:
        lines.append("  field order differs")
        lines.append(f"    actual:   {list(actual.names)}")
        lines.append(f"    expected: {list(expected.names)}")
    return "\n".join(lines) if lines else "  (no field-level diff; check metadata)"
