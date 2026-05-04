"""Stress scenarios — formal implementation of `docs/SCENARIOS.md §3`.

Each scenario module exposes:
    - a Pydantic-or-dataclass Config type
    - a `stress_<sN>(state, config) -> Trajectory` entrypoint
    - scenario-specific output metric helpers

Common types live in `state.py`, `trajectory.py`, and `liquidation.py`.
"""

from morpho_stress.scenarios.liquidation import (
    LiquidationOutcome,
    liquidate_all_eligible,
    liquidate_position,
    liquidation_incentive_factor,
)
from morpho_stress.scenarios.s1_withdrawal import (
    S1Config,
    stress_s1,
    time_to_illiquid,
)
from morpho_stress.scenarios.state import (
    MarketParams,
    MarketState,
    Position,
    assert_invariants,
)
from morpho_stress.scenarios.trajectory import ScenarioResult, Trajectory

__all__ = [
    "LiquidationOutcome",
    "MarketParams",
    "MarketState",
    "Position",
    "S1Config",
    "ScenarioResult",
    "Trajectory",
    "assert_invariants",
    "liquidate_all_eligible",
    "liquidate_position",
    "liquidation_incentive_factor",
    "stress_s1",
    "time_to_illiquid",
]
