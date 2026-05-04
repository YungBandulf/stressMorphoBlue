"""Scenario S1 — Withdrawal Run.

Spec: `docs/SCENARIOS.md §3, S1`.

A fraction `alpha` of suppliers attempt to withdraw their balance over `T`
blocks. Withdrawals are honored as long as `L_t >= W_requested(t)`; otherwise
the unhonored portion accumulates in `queued_withdrawals`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from morpho_stress.models.constants import BLOCK_TIME_SEC
from morpho_stress.models.irm import IrmParams, accrue
from morpho_stress.scenarios.state import MarketState
from morpho_stress.scenarios.trajectory import Trajectory


@dataclass(frozen=True, slots=True)
class S1Config:
    """Parameters for the withdrawal-run scenario."""

    alpha: float  # fraction of total supply to withdraw, [0, 1]
    duration_blocks: int  # T
    horizon_blocks: int  # h
    arrival: str = "linear"  # "linear" | "exponential"
    behavior: str = "no_response"  # "no_response" | "rate_response"


def _withdrawal_schedule(
    initial_supply: float, alpha: float, duration: int, arrival: str
) -> np.ndarray:
    """Generate per-block withdrawal request amounts.

    Returns an array of length `duration + 1` where index 0 is the initial
    block (no withdrawal) and indices 1..duration are the per-block requests.
    """
    if alpha < 0 or alpha > 1:
        raise ValueError(f"alpha must be in [0, 1], got {alpha}")
    if duration < 1:
        raise ValueError(f"duration must be >= 1, got {duration}")

    total_to_withdraw = initial_supply * alpha
    schedule = np.zeros(duration + 1, dtype=float)

    if arrival == "linear":
        per_block = total_to_withdraw / duration
        schedule[1:] = per_block
    elif arrival == "exponential":
        # Front-loaded: half-life = duration / 4
        half_life = duration / 4.0
        decay = math.log(2.0) / half_life
        weights = np.exp(-decay * np.arange(duration))
        weights = weights / weights.sum()
        schedule[1:] = total_to_withdraw * weights
    else:
        raise ValueError(f"unknown arrival pattern: {arrival}")

    return schedule


def stress_s1(initial_state: MarketState, cfg: S1Config) -> Trajectory:
    """Run the S1 withdrawal-run stress on `initial_state`.

    Returns a `Trajectory` of length `horizon_blocks + 1`.
    """
    schedule = _withdrawal_schedule(
        initial_state.total_supply_assets,
        cfg.alpha,
        cfg.duration_blocks,
        cfg.arrival,
    )

    irm_params = IrmParams(
        target_utilization=initial_state.params.irm_target_utilization,
        curve_steepness=initial_state.params.irm_curve_steepness,
        adjustment_speed=initial_state.params.irm_adjustment_speed,
        initial_rate_at_target=initial_state.params.irm_initial_rate_at_target,
    )

    traj = Trajectory()
    traj.append(initial_state)

    state = initial_state
    horizon = cfg.horizon_blocks

    for k in range(1, horizon + 1):
        # 1. Accrue interest from previous block (with adaptive rate_at_target update)
        new_supply, new_borrow, new_rate = accrue(
            state.total_supply_assets,
            state.total_borrow_assets,
            state.params.fee,
            state.rate_at_target,
            irm_params,
            elapsed_seconds=BLOCK_TIME_SEC,
        )

        # 2. Apply withdrawal request for this block
        due = schedule[k] if k < len(schedule) else 0.0
        liquidity_after_accrual = max(0.0, new_supply - new_borrow)
        honored = min(due, liquidity_after_accrual)
        unhonored = due - honored

        new_supply_after_w = new_supply - honored

        new_state = state.replace(
            block=state.block + 1,
            block_ts=state.block_ts + BLOCK_TIME_SEC,
            total_supply_assets=new_supply_after_w,
            total_borrow_assets=new_borrow,
            rate_at_target=new_rate,
            queued_withdrawals=state.queued_withdrawals + unhonored,
        )

        traj.append(new_state)
        if unhonored > 0:
            traj.events.append(
                {
                    "block": new_state.block,
                    "kind": "withdrawal_unhonored",
                    "requested": float(due),
                    "honored": float(honored),
                    "unhonored": float(unhonored),
                }
            )

        state = new_state

    return traj


def time_to_illiquid(traj: Trajectory) -> int | None:
    """First block index where queued_withdrawals > 0. None if never."""
    for state in traj.states:
        if state.queued_withdrawals > 0:
            return state.block - traj.states[0].block
    return None
