"""Tests for the pipeline manifest."""

from __future__ import annotations

from pathlib import Path

from morpho_stress.data.manifest import (
    FileEntry,
    Manifest,
    RunEntry,
    ValidationResult,
)


def _sample_run() -> RunEntry:
    return RunEntry(
        run_id=Manifest.now_run_id(),
        run_ts="2026-05-04T08:00:00Z",
        config_hash=Manifest.hash_config({"foo": 1, "bar": [2, 3]}),
        block_range_min=21_900_000,
        block_range_max=22_100_000,
        markets=["0x" + "a" * 64],
        files={
            "markets.parquet": FileEntry(
                path="data/cache/markets.parquet",
                schema="markets",
                rows=17,
                bytes=12_450,
                sha256="0" * 64,
            ),
        },
        validation=ValidationResult(all_passed=True, warnings=[]),
    )


def test_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    m = Manifest(path)
    m.append_run(_sample_run())

    # Re-load from disk.
    m2 = Manifest(path)
    latest = m2.latest_run()
    assert latest is not None
    assert latest["block_range_min"] == 21_900_000
    assert latest["files"]["markets.parquet"]["rows"] == 17


def test_manifest_append_only(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    m = Manifest(path)
    run1 = _sample_run()
    m.append_run(run1)
    run2 = _sample_run()
    m.append_run(run2)

    m2 = Manifest(path)
    assert len(m2._data["runs"]) == 2  # noqa: SLF001 — test introspects implementation


def test_config_hash_stable() -> None:
    """Same config dict ⇒ same hash regardless of key order."""
    h1 = Manifest.hash_config({"a": 1, "b": 2})
    h2 = Manifest.hash_config({"b": 2, "a": 1})
    assert h1 == h2


def test_config_hash_changes_on_mutation() -> None:
    h1 = Manifest.hash_config({"a": 1, "b": 2})
    h2 = Manifest.hash_config({"a": 1, "b": 3})
    assert h1 != h2
