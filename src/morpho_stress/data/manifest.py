"""Pipeline manifest — tracks every successful data acquisition run.

The manifest is the single source of truth for "what data version is on disk."
Phase 3 modeling code reads the latest manifest entry to pin its inputs and
detect drift. Manifest is append-only; never mutate past entries.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class FileEntry:
    path: str
    schema: str
    rows: int
    bytes: int
    sha256: str


@dataclass
class ValidationResult:
    all_passed: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class RunEntry:
    run_id: str
    run_ts: str
    config_hash: str
    block_range_min: int
    block_range_max: int
    markets: list[str]
    files: dict[str, FileEntry]
    validation: ValidationResult


class Manifest:
    SCHEMA_VERSION = "0.1"

    def __init__(self, path: str | Path = "data/manifest.json") -> None:
        self._path = Path(path)
        self._data: dict[str, Any] = (
            json.loads(self._path.read_text())
            if self._path.exists()
            else {"schema_version": self.SCHEMA_VERSION, "runs": []}
        )

    def append_run(self, run: RunEntry) -> None:
        self._data["runs"].append(self._serialize_run(run))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def latest_run(self) -> dict[str, Any] | None:
        runs = self._data.get("runs", [])
        return runs[-1] if runs else None

    @staticmethod
    def _serialize_run(run: RunEntry) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "run_ts": run.run_ts,
            "config_hash": run.config_hash,
            "block_range_min": run.block_range_min,
            "block_range_max": run.block_range_max,
            "markets": run.markets,
            "files": {name: asdict(entry) for name, entry in run.files.items()},
            "validation": asdict(run.validation),
        }

    @staticmethod
    def hash_config(config_dict: dict[str, Any]) -> str:
        """Stable hash of a config dict (sorted keys, no whitespace)."""
        blob = json.dumps(config_dict, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(blob).hexdigest()

    @staticmethod
    def now_run_id() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
