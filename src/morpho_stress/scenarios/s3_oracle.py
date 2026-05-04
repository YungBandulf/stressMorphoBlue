"""Scenario S3 — Oracle Deviation.

Spec: `docs/SCENARIOS.md §3, S3`.

Collateral price drops by ``Delta`` over window ``Delta_t``. Oracle reports a
possibly-lagged price (TWAP smoothing or pure passthrough depending on
``oracle_kind``). At each block:

1. Accrue interest (with adaptive rate update)
2. Evolve market price along the drawdown path
3. Update oracle with current market price
4. Identify liquidatable positions at oracle price
5. Liquidate eligible positions, computing realized recovery on DEX at market
   price discounted by slippage curve

Two regimes (per `docs/SCENARIOS.md §2.3`):

- **Exogenous** (default for Chainlink, Pyth): oracle = market price (with
  optional configurable lag in blocks).
- **Endogenous** (for `uniswap_twap`): oracle is geometric TWAP of market;
  liquidator selling moves the *market*, which feeds back into the oracle
  through TWAP smoothing.

For S3 we model the **exogenous** regime (oracle drives liquidations but
liquidator selling does NOT move market price). S4 will add the endogenous
feedback.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from morpho_stress.models.constants import BLOCK_TIME_SEC
from morpho_stress.models.irm import IrmParams, accrue
from morpho_stress.models.oracle import ExogenousOracle, Oracle, TwapOracle, make_oracle
from morpho_stress.models.slippage import SlippageCurve
from morpho_stress.scenarios.liquidation import liquidate_all_eligible
from morpho_stress.scenarios.state import MarketState
from morpho_stress.scenarios.trajectory import Trajectory


@dataclass(frozen=True, slots=True)
class S3Config:
    """Parameters for the oracle-deviation scenario.

    Attributes:
        drawdown: total fractional price drop over `dt_blocks`. 0.30 = -30%.
        dt_blocks: number of blocks over which the drawdown unfolds.
        horizon_blocks: total simulation horizon (must be >= dt_blocks).
        shape: drawdown shape, "linear" or "instant" (step at block 1).
        oracle_lag_blocks: optional extra lag for exogenous oracle. 0 = no lag.
            For TWAP oracle, this is the lambda_blocks window.
        regime: "exogenous" (default) or "endogenous". Endogenous activates
            DEX feedback into market price (used in S4, but available here).
    """

    drawdown: float
    dt_blocks: int
    horizon_blocks: int
    shape: str = "linear"
    oracle_lag_blocks: int = 0
    regime: str = "exogenous"


def _drawdown_path(initial_price: float, drawdown: float, dt_blocks: int, shape: str) -> np.ndarray:
    """Generate per-block market price path over the drawdown window.

    Returns an array of length `dt_blocks + 1`, indexed by block offset from
    the start. Index 0 is the initial price; index dt_blocks is at the floor
    of the drawdown.
    """
    if not (0.0 <= drawdown < 1.0):
        raise ValueError(f"drawdown must be in [0, 1), got {drawdown}")
    if dt_blocks < 1:
        raise ValueError(f"dt_blocks must be >= 1, got {dt_blocks}")

    floor_price = initial_price * (1.0 - drawdown)
    path = np.empty(dt_blocks + 1, dtype=float)
    path[0] = initial_price

    if shape == "linear":
        path[1:] = np.linspace(initial_price, floor_price, dt_blocks + 1)[1:]
    elif shape == "instant":
        path[1:] = floor_price
    else:
        raise ValueError(f"unknown shape: {shape}")

    return path


def _make_oracle_for_state(state: MarketState, lag_blocks: int) -> Oracle:
    """Construct an oracle compatible with the state's configured kind."""
    kind = state.params.oracle_kind
    if kind == "uniswap_twap":
        # Use lag_blocks as the TWAP window (defaults: 60 if 0)
        return TwapOracle(
            initial_price=state.oracle_price,
            lambda_blocks=max(1, lag_blocks if lag_blocks > 0 else 60),
        )
    return ExogenousOracle(initial_price=state.oracle_price)


def stress_s3(
    initial_state: MarketState,
    cfg: S3Config,
    slippage_curve: SlippageCurve,
) -> Trajectory:
    """Run the S3 oracle-deviation stress on `initial_state`.

    Returns a `Trajectory` of length `horizon_blocks + 1`.
    """
    if cfg.horizon_blocks < cfg.dt_blocks:
        raise ValueError(
            f"horizon_blocks ({cfg.horizon_blocks}) must be >= dt_blocks ({cfg.dt_blocks})"
        )

    market_path = _drawdown_path(
        initial_state.oracle_price, cfg.drawdown, cfg.dt_blocks, cfg.shape
    )
    # Extend path beyond dt_blocks with constant floor price
    if cfg.horizon_blocks > cfg.dt_blocks:
        floor = market_path[-1]
        full_market_path = np.concatenate(
            [market_path, np.full(cfg.horizon_blocks - cfg.dt_blocks, floor)]
        )
    else:
        full_market_path = market_path

    oracle = _make_oracle_for_state(initial_state, cfg.oracle_lag_blocks)

    irm_params = IrmParams(
        target_utilization=initial_state.params.irm_target_utilization,
        curve_steepness=initial_state.params.irm_curve_steepness,
        adjustment_speed=initial_state.params.irm_adjustment_speed,
        initial_rate_at_target=initial_state.params.irm_initial_rate_at_target,
    )

    traj = Trajectory()
    traj.append(initial_state)
    state = initial_state

    for k in range(1, cfg.horizon_blocks + 1):
        # 1. Accrue interest (and update rate_at_target via adaptive layer)
        new_supply, new_borrow, new_rate = accrue(
            state.total_supply_assets,
            state.total_borrow_assets,
            state.params.fee,
            state.rate_at_target,
            irm_params,
            elapsed_seconds=BLOCK_TIME_SEC,
        )

        # 2. Evolve market price
        market_price = float(full_market_path[k] if k < len(full_market_path) else full_market_path[-1])

        # 3. Update oracle with current market price
        oracle.update(market_price, block=k)
        new_oracle_price = oracle.read()

        # 4. Build pre-liquidation state at the new oracle price
        pre_liq_state = state.replace(
            block=state.block + 1,
            block_ts=state.block_ts + BLOCK_TIME_SEC,
            total_supply_assets=new_supply,
            total_borrow_assets=new_borrow,
            rate_at_target=new_rate,
            oracle_price=new_oracle_price,
        )

        # 5. Liquidate eligible positions
        outcomes, post_liq_state = liquidate_all_eligible(
            pre_liq_state,
            market_price=market_price,  # liquidator sells at market, not oracle
            slippage_curve=slippage_curve,
        )

        # Log liquidation events
        for outcome in outcomes:
            traj.events.append(
                {
                    "block": post_liq_state.block,
                    "kind": "liquidation",
                    "borrower": outcome.borrower,
                    "repaid_assets": outcome.repaid_assets,
                    "seized_collateral": outcome.seized_collateral,
                    "realized_loan_value": outcome.realized_loan_value,
                    "bad_debt_assets": outcome.bad_debt_assets,
                }
            )

        traj.append(post_liq_state)
        state = post_liq_state

    return traj


def n_liquidated(traj: Trajectory) -> int:
    """Count liquidation events in a trajectory."""
    return sum(1 for e in traj.events if e["kind"] == "liquidation")


def total_bad_debt(traj: Trajectory) -> float:
    """Sum of realized bad debt across all liquidation events."""
    return float(traj.final_state.realized_bad_debt)


def cascade_depth(traj: Trajectory) -> int:
    """Maximum number of liquidations occurring in a single block."""
    if not traj.events:
        return 0
    counts: dict[int, int] = {}
    for e in traj.events:
        if e["kind"] == "liquidation":
            counts[e["block"]] = counts.get(e["block"], 0) + 1
    return max(counts.values()) if counts else 0


def slippage_shortfall(traj: Trajectory) -> float:
    """Sum of (repaid - realized) across liquidations.

    This captures the gap between the loan-asset value the liquidator was
    supposed to recover and what they actually received after DEX slippage.
    """
    return sum(
        max(0.0, e["repaid_assets"] - e["realized_loan_value"])
        for e in traj.events
        if e["kind"] == "liquidation"
    )
