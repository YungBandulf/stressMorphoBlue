"""Backtest fixture loader — reads versioned event fixtures from disk.

Each event fixture is a directory under `data/fixtures/<event_id>/` with:
    event.yaml   — metadata
    market.json  — Morpho Blue market parameters at T-1
    prices.csv   — hourly oracle + market price series

The loader produces a fully-typed `EventFixture` ready for stress-testing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from morpho_stress.scenarios.state import MarketParams, MarketState, Position


@dataclass(frozen=True, slots=True)
class EventMeta:
    """Event metadata loaded from event.yaml."""

    event_id: str
    event_name: str
    event_ts: datetime
    t0_ts: datetime
    affected_collaterals: tuple[str, ...]
    affected_loan_assets: tuple[str, ...]
    counterfactual: bool
    expected_red_flag: bool
    notes: str = ""


@dataclass(frozen=True, slots=True)
class EventFixture:
    """Complete fixture for a single backtest event."""

    meta: EventMeta
    initial_state: MarketState
    prices: pd.DataFrame  # columns: ts, symbol, market_price_usd, oracle_price_usd, source
    fixture_path: Path

    @property
    def event_id(self) -> str:
        return self.meta.event_id

    @property
    def market_path(self) -> np.ndarray:
        """Hourly market price array, indexed from window start."""
        return self.prices["market_price_usd"].to_numpy()

    @property
    def oracle_path(self) -> np.ndarray:
        """Hourly oracle price array."""
        return self.prices["oracle_price_usd"].to_numpy()

    @property
    def price_timestamps(self) -> pd.DatetimeIndex:
        """UTC timestamps for each price observation."""
        return pd.DatetimeIndex(pd.to_datetime(self.prices["ts"], utc=True))

    def t0_index(self) -> int:
        """Index of T0 in the price array."""
        ts = self.price_timestamps
        # Find first observation >= t0_ts
        t0 = pd.Timestamp(self.meta.t0_ts)
        mask = ts >= t0
        if not mask.any():
            raise ValueError(f"T0 {t0} not found in price window")
        return int(np.argmax(mask))


def load_event(fixture_dir: Path | str) -> EventFixture:
    """Load a single event fixture from disk."""
    fixture_dir = Path(fixture_dir)
    if not fixture_dir.is_dir():
        raise FileNotFoundError(f"fixture directory not found: {fixture_dir}")

    # event.yaml
    with (fixture_dir / "event.yaml").open() as f:
        meta_raw = yaml.safe_load(f)

    # The yaml dates may parse as datetime or str; coerce both
    event_ts = _coerce_dt(meta_raw["event_ts"])
    t0_ts = _coerce_dt(meta_raw["t0_ts"])

    meta = EventMeta(
        event_id=str(meta_raw["event_id"]),
        event_name=str(meta_raw["event_name"]),
        event_ts=event_ts,
        t0_ts=t0_ts,
        affected_collaterals=tuple(meta_raw["affected_collaterals"]),
        affected_loan_assets=tuple(meta_raw["affected_loan_assets"]),
        counterfactual=bool(meta_raw["counterfactual"]),
        expected_red_flag=bool(meta_raw["expected_red_flag"]),
        notes=str(meta_raw.get("notes", "")),
    )

    # market.json
    with (fixture_dir / "market.json").open() as f:
        m = json.load(f)

    initial_state = _build_market_state_from_fixture(m)

    # prices.csv
    prices = pd.read_csv(fixture_dir / "prices.csv")
    if not {"ts", "symbol", "market_price_usd", "oracle_price_usd"}.issubset(prices.columns):
        raise ValueError(f"prices.csv missing required columns: {prices.columns.tolist()}")

    return EventFixture(meta=meta, initial_state=initial_state, prices=prices, fixture_path=fixture_dir)


def _coerce_dt(value: str | datetime) -> datetime:
    """Accept ISO string or datetime, return tz-aware datetime."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _build_market_state_from_fixture(m: dict) -> MarketState:
    """Construct a MarketState from a fixture market.json record.

    Position-level state is synthesized deterministically from the
    `n_positions_seed` field, with LTVs sampled to be just below LLTV
    (representative of an active borrow market at peak utilization).
    """
    n_pos = int(m["n_positions_seed"])
    lltv = float(m["lltv"])
    total_borrow = float(m["total_borrow_assets"])
    total_collateral_usd = total_borrow / (0.7 * float(m["oracle_price_at_snapshot"]))  # avg LTV ~0.7

    rng = np.random.default_rng(int(m["snapshot_block"]) % (2**32))
    weights = rng.dirichlet(np.ones(n_pos))
    pos_borrow = total_borrow * weights

    # Sample LTV per position
    ltvs = np.clip(rng.normal(0.7, 0.08, n_pos), 0.05, lltv - 1e-4)
    pos_collateral = pos_borrow / (ltvs * float(m["oracle_price_at_snapshot"]))

    positions = tuple(
        Position(
            borrower="0x" + f"{(int(m['snapshot_block']) * 1000003 + i) % (1 << 160):040x}",
            collateral=float(pos_collateral[i]),
            borrow_shares=float(pos_borrow[i]),
        )
        for i in range(n_pos)
    )

    params = MarketParams(
        market_id=str(m["market_id"]),
        loan_decimals=int(m["loan_asset_decimals"]),
        collateral_decimals=int(m["collateral_asset_decimals"]),
        lltv=lltv,
        fee=float(m.get("fee", 0.0)),
        irm_target_utilization=float(m.get("irm_target_utilization", 0.9)),
        irm_curve_steepness=float(m.get("irm_curve_steepness", 4.0)),
        irm_adjustment_speed=float(m.get("irm_adjustment_speed", 50.0)),
        irm_initial_rate_at_target=float(m["rate_at_target_at_snapshot"]),
        oracle_kind=str(m.get("oracle_kind", "chainlink")),
    )

    snapshot_ts = _coerce_dt(m["snapshot_ts"])

    return MarketState(
        params=params,
        block=int(m["snapshot_block"]),
        block_ts=int(snapshot_ts.timestamp()),
        total_supply_assets=float(m["total_supply_assets"]),
        total_supply_shares=float(m["total_supply_shares"]),
        total_borrow_assets=float(m["total_borrow_assets"]),
        total_borrow_shares=float(m["total_borrow_shares"]),
        total_collateral=float(pos_collateral.sum()),
        oracle_price=float(m["oracle_price_at_snapshot"]),
        rate_at_target=float(m["rate_at_target_at_snapshot"]),
        positions=positions,
    )


def list_fixtures(root: Path | str = "data/fixtures") -> list[str]:
    """List available event_ids by scanning fixture directories."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and (d / "event.yaml").exists()
    )
