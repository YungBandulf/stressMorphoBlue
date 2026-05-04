"""Tests for the typed Config loader."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from morpho_stress.config import Config


VALID_CONFIG = {
    "network": {
        "chain_id": 1,
        "rpc_url": "https://eth-mainnet.example/v2/key",
        "rpc_url_fallback": "https://fallback.example",
    },
    "morpho_blue": {"contract": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFFb"},
    "subgraph": {"url": "https://api.thegraph.com/morpho-blue"},
    "oneinch": {"api_url": "https://api.1inch.dev/swap/v6.0/1"},
    "sampling": {
        "market_state_period_blocks": 1800,
        "oracle_price_period_blocks": 300,
        "position_snapshot_period_blocks": 7200,
    },
    "range": {
        "start_ts": "2025-05-01T00:00:00Z",
        "end_ts": "2026-05-01T00:00:00Z",
    },
    "markets": ["0x" + "a" * 64],
}


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.local.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path, VALID_CONFIG)
    cfg = Config.load(path)
    assert cfg.network.chain_id == 1
    assert cfg.sampling.market_state_period_blocks == 1800
    assert len(cfg.markets) == 1


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Config.load(tmp_path / "nope.yaml")


def test_invalid_market_id(tmp_path: Path) -> None:
    bad = dict(VALID_CONFIG)
    bad["markets"] = ["0xdeadbeef"]  # too short
    path = _write_yaml(tmp_path, bad)
    with pytest.raises(Exception):  # pydantic.ValidationError
        Config.load(path)


def test_range_order_enforced(tmp_path: Path) -> None:
    bad = dict(VALID_CONFIG)
    bad["range"] = {"start_ts": "2026-05-01T00:00:00Z", "end_ts": "2025-05-01T00:00:00Z"}
    path = _write_yaml(tmp_path, bad)
    with pytest.raises(Exception):
        Config.load(path)


def test_env_var_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALCHEMY_KEY", "secret-abc-123")
    cfg_data = dict(VALID_CONFIG)
    cfg_data["network"] = dict(cfg_data["network"])
    cfg_data["network"]["rpc_url"] = "https://eth-mainnet.example/v2/${ALCHEMY_KEY}"
    path = _write_yaml(tmp_path, cfg_data)
    cfg = Config.load(path)
    assert "secret-abc-123" in cfg.network.rpc_url


def test_missing_env_var_returns_none_for_optional_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GRAPH_API_KEY", raising=False)
    cfg_data = dict(VALID_CONFIG)
    cfg_data["subgraph"] = dict(cfg_data["subgraph"])
    cfg_data["subgraph"]["api_key"] = "${GRAPH_API_KEY}"
    path = _write_yaml(tmp_path, cfg_data)
    cfg = Config.load(path)
    assert cfg.subgraph.api_key is None
