"""Trajectory and result types for stress scenario simulations."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from morpho_stress.scenarios.state import MarketState


@dataclass
class Trajectory:
    """Sequence of market states across the stress horizon, plus event log."""

    states: list[MarketState] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)  # liquidations, withdrawals, etc.

    def append(self, state: MarketState) -> None:
        self.states.append(state)

    def to_frame(self) -> pd.DataFrame:
        """Flat DataFrame for analysis / plotting."""
        return pd.DataFrame([s.to_dict() for s in self.states])

    @property
    def horizon(self) -> int:
        return len(self.states) - 1 if self.states else 0

    @property
    def final_state(self) -> MarketState:
        if not self.states:
            raise ValueError("empty trajectory")
        return self.states[-1]


@dataclass
class ScenarioResult:
    """Output metrics for a single (market, scenario, horizon) tuple."""

    scenario_id: str
    market_id: str
    horizon_blocks: int

    # Core metrics
    lcr_onchain: float | None  # None if not computed
    time_to_illiquid: int | None  # block index, None if never
    expected_bad_debt: float
    slippage_shortfall: float
    cascade_depth: int
    feedback_amplification: float | None
    severity_flag: str  # green / yellow / red

    # Optional richer output
    trajectory: Trajectory | None = None

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "market_id": self.market_id,
            "horizon_blocks": self.horizon_blocks,
            "lcr_onchain": self.lcr_onchain,
            "time_to_illiquid": self.time_to_illiquid,
            "expected_bad_debt": self.expected_bad_debt,
            "slippage_shortfall": self.slippage_shortfall,
            "cascade_depth": self.cascade_depth,
            "feedback_amplification": self.feedback_amplification,
            "severity_flag": self.severity_flag,
        }
