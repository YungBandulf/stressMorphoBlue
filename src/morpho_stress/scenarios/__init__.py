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
from morpho_stress.scenarios.montecarlo import (
    EmpiricalDistribution,
    McResult,
    joint_mc,
    run_monte_carlo,
)
from morpho_stress.scenarios.s1_withdrawal import (
    S1Config,
    stress_s1,
    time_to_illiquid,
)
from morpho_stress.scenarios.s3_oracle import (
    S3Config,
    cascade_depth,
    n_liquidated,
    slippage_shortfall,
    stress_s3,
    total_bad_debt,
)
from morpho_stress.scenarios.state import (
    MarketParams,
    MarketState,
    Position,
    assert_invariants,
)
from morpho_stress.scenarios.trajectory import ScenarioResult, Trajectory

__all__ = [
    "EmpiricalDistribution",
    "LiquidationOutcome",
    "MarketParams",
    "MarketState",
    "McResult",
    "Position",
    "S1Config",
    "S3Config",
    "ScenarioResult",
    "Trajectory",
    "assert_invariants",
    "cascade_depth",
    "joint_mc",
    "liquidate_all_eligible",
    "liquidate_position",
    "liquidation_incentive_factor",
    "n_liquidated",
    "run_monte_carlo",
    "slippage_shortfall",
    "stress_s1",
    "stress_s3",
    "time_to_illiquid",
    "total_bad_debt",
]
