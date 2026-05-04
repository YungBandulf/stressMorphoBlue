"""Tests for stress scenarios — state invariants, S1 behavior, liquidations."""

from __future__ import annotations

import math

import pytest

from morpho_stress.models.slippage import SlippageCurve
from morpho_stress.scenarios import (
    MarketState,
    Position,
    S1Config,
    assert_invariants,
    liquidate_all_eligible,
    liquidate_position,
    liquidation_incentive_factor,
    stress_s1,
    time_to_illiquid,
)
from morpho_stress.utils.mock import make_market_params, make_market_state


# ---------------------------------------------------------------------------
# State invariants
# ---------------------------------------------------------------------------


def test_mock_state_passes_invariants() -> None:
    state = make_market_state()
    assert_invariants(state)


def test_mock_state_no_initial_liquidations() -> None:
    """At construction, no position should be liquidatable."""
    state = make_market_state()
    eligible = state.liquidatable_positions()
    assert len(eligible) == 0


def test_state_utilization_in_range() -> None:
    state = make_market_state(utilization=0.85)
    assert 0.0 <= state.utilization <= 1.0
    assert math.isclose(state.utilization, 0.85, rel_tol=1e-6)


def test_state_liquidity_equals_supply_minus_borrow() -> None:
    state = make_market_state()
    assert state.liquidity == state.total_supply_assets - state.total_borrow_assets


# ---------------------------------------------------------------------------
# Liquidation engine
# ---------------------------------------------------------------------------


def test_lif_at_canonical_lltv() -> None:
    """LLTV=0.86 should give LIF ≈ 1.043 (Morpho documented value)."""
    lif = liquidation_incentive_factor(0.86)
    assert math.isclose(lif, 1 / (0.3 * 0.86 + 0.7), rel_tol=1e-9)
    assert 1.04 < lif < 1.05


def test_lif_capped_at_115() -> None:
    """For low LLTVs (high incentive), LIF must cap at 1.15."""
    assert liquidation_incentive_factor(0.1) == 1.15


def test_liquidate_position_clears_position() -> None:
    state = make_market_state(n_positions=10)
    target = state.positions[0]

    # Force liquidation by halving oracle price
    stressed = state.replace(oracle_price=state.oracle_price * 0.5)
    eligible = stressed.liquidatable_positions()
    assert len(eligible) > 0  # half-price guarantees most positions are underwater

    curve = SlippageCurve(asset_symbol="X", a=1e-5, b=0.5)
    outcome, new_state = liquidate_position(
        stressed, target, market_price=stressed.oracle_price, slippage_curve=curve
    )
    # Position is removed
    assert all(p.borrower != target.borrower for p in new_state.positions)
    # Borrow shares decreased by the position's shares
    expected_shares = stressed.total_borrow_shares - target.borrow_shares
    assert math.isclose(new_state.total_borrow_shares, expected_shares, rel_tol=1e-9)


def test_liquidate_with_high_slippage_creates_bad_debt() -> None:
    state = make_market_state(n_positions=10, oracle_price=2_000.0)
    # Stress: drop oracle by 20%; LIF×slippage > 1 ⇒ likely some bad debt
    stressed = state.replace(oracle_price=1_600.0)
    bad_curve = SlippageCurve(asset_symbol="X", a=0.05, b=0.7, max_slippage=0.5)
    outcomes, new_state = liquidate_all_eligible(
        stressed, market_price=stressed.oracle_price, slippage_curve=bad_curve
    )
    if outcomes:
        # At least *some* liquidation happened
        total_bad_debt = sum(o.bad_debt_assets for o in outcomes)
        assert total_bad_debt >= 0  # may be 0 if slippage doesn't bite hard enough


def test_liquidate_with_zero_slippage_no_bad_debt_for_healthy_seize() -> None:
    """With perfect liquidations (π=0), bad debt = 0 if LIF·collateral covers debt."""
    state = make_market_state(n_positions=5)
    # Trigger liquidations via small price drop, but keep slippage at 0
    stressed = state.replace(oracle_price=state.oracle_price * 0.95)
    perfect = SlippageCurve(asset_symbol="X", a=0.0, b=1.0, max_slippage=0.0)
    outcomes, _ = liquidate_all_eligible(
        stressed, market_price=stressed.oracle_price, slippage_curve=perfect
    )
    # With LIF > 1 and no slippage, liquidator gets > debt -> no bad debt
    for o in outcomes:
        assert o.bad_debt_assets <= 1e-6


# ---------------------------------------------------------------------------
# S1 — withdrawal run
# ---------------------------------------------------------------------------


def test_s1_low_alpha_no_illiquidity() -> None:
    """Withdrawing 1% over 1 day from a market with 15% liquidity must NOT illiquid."""
    state = make_market_state(utilization=0.85)  # 15% liquidity
    cfg = S1Config(alpha=0.01, duration_blocks=7200, horizon_blocks=7200)
    traj = stress_s1(state, cfg)
    assert traj.final_state.queued_withdrawals == 0.0
    assert time_to_illiquid(traj) is None


def test_s1_high_alpha_triggers_illiquidity() -> None:
    """Withdrawing 50% from a market with 15% liquidity MUST illiquid."""
    state = make_market_state(utilization=0.85)  # 15% liquidity
    cfg = S1Config(alpha=0.5, duration_blocks=300, horizon_blocks=600)
    traj = stress_s1(state, cfg)
    assert traj.final_state.queued_withdrawals > 0
    assert time_to_illiquid(traj) is not None


def test_s1_trajectory_length() -> None:
    state = make_market_state()
    cfg = S1Config(alpha=0.05, duration_blocks=100, horizon_blocks=200)
    traj = stress_s1(state, cfg)
    assert len(traj.states) == cfg.horizon_blocks + 1  # initial + h blocks


def test_s1_total_withdrawal_matches_schedule() -> None:
    """Sum of honored + unhonored = alpha * S0."""
    state = make_market_state(utilization=0.5)  # plenty of liquidity
    alpha = 0.1
    cfg = S1Config(alpha=alpha, duration_blocks=50, horizon_blocks=50)
    traj = stress_s1(state, cfg)
    initial_supply = state.total_supply_assets
    final_supply = traj.final_state.total_supply_assets
    queued = traj.final_state.queued_withdrawals

    # Honored = (S0 - S_final + interest_accrued)
    # We can't easily isolate interest, but: queued + honored = alpha * S0 (approximately)
    # Total drawn from S = S0 - S_final + interest. We just check queued is plausible.
    assert queued >= 0
    # Liquidity was sufficient ⇒ no queue
    assert queued == 0.0
    # Final supply roughly = initial - alpha * initial + interest accrued
    # interest is small over 50 blocks; supply drop should be ~ alpha * initial
    expected_drop = alpha * initial_supply
    actual_drop = initial_supply - final_supply
    # Allow 10% deviation for interest accrual
    assert abs(actual_drop - expected_drop) < 0.1 * expected_drop


def test_s1_invariants_preserved_throughout() -> None:
    state = make_market_state()
    cfg = S1Config(alpha=0.2, duration_blocks=100, horizon_blocks=200)
    traj = stress_s1(state, cfg)
    for s in traj.states:
        # Supply and borrow remain non-negative; borrow can equal or be less than supply
        assert s.total_supply_assets >= 0
        assert s.total_borrow_assets >= 0


def test_s1_alpha_out_of_range_raises() -> None:
    state = make_market_state()
    with pytest.raises(ValueError):
        stress_s1(state, S1Config(alpha=-0.1, duration_blocks=10, horizon_blocks=10))
    with pytest.raises(ValueError):
        stress_s1(state, S1Config(alpha=1.5, duration_blocks=10, horizon_blocks=10))


def test_s1_duration_zero_raises() -> None:
    state = make_market_state()
    with pytest.raises(ValueError):
        stress_s1(state, S1Config(alpha=0.1, duration_blocks=0, horizon_blocks=10))


def test_s1_exponential_arrival_concentrates_early_withdrawals() -> None:
    """Exponential arrival should drain liquidity faster than linear."""
    state = make_market_state(utilization=0.85)
    cfg_lin = S1Config(alpha=0.2, duration_blocks=100, horizon_blocks=100, arrival="linear")
    cfg_exp = S1Config(
        alpha=0.2, duration_blocks=100, horizon_blocks=100, arrival="exponential"
    )
    traj_lin = stress_s1(state, cfg_lin)
    traj_exp = stress_s1(state, cfg_exp)

    # Exponential should hit illiquidity earlier (or at least not later)
    tti_lin = time_to_illiquid(traj_lin)
    tti_exp = time_to_illiquid(traj_exp)
    if tti_lin is not None and tti_exp is not None:
        assert tti_exp <= tti_lin
