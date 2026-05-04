"""Tests for scenario S3 — oracle deviation."""

from __future__ import annotations

import pytest

from morpho_stress.models.slippage import SlippageCurve
from morpho_stress.scenarios import (
    S3Config,
    cascade_depth,
    n_liquidated,
    slippage_shortfall,
    stress_s3,
    total_bad_debt,
)
from morpho_stress.utils.mock import make_market_state


@pytest.fixture
def state():
    return make_market_state(
        initial_supply=100_000_000.0,
        utilization=0.85,
        oracle_price=2_000.0,
        n_positions=100,
        avg_ltv=0.7,
        ltv_std=0.1,
        seed=42,
    )


@pytest.fixture
def curve():
    return SlippageCurve(asset_symbol="WETH", a=2e-4, b=0.55)


# ---------------------------------------------------------------------------
# Drawdown path
# ---------------------------------------------------------------------------


def test_s3_no_drawdown_no_liquidations(state, curve) -> None:
    """drawdown=0 should produce zero liquidations."""
    cfg = S3Config(drawdown=0.0, dt_blocks=10, horizon_blocks=10)
    traj = stress_s3(state, cfg, curve)
    assert n_liquidated(traj) == 0
    assert total_bad_debt(traj) == 0.0


def test_s3_small_drawdown_few_liquidations(state, curve) -> None:
    """Small drawdown only liquidates positions near LLTV."""
    cfg = S3Config(drawdown=0.05, dt_blocks=10, horizon_blocks=20)
    traj = stress_s3(state, cfg, curve)
    n = n_liquidated(traj)
    # With LLTV=0.86, avg LTV=0.7, std=0.1: a 5% drop pushes some positions
    # at LTV ~ 0.82 above LLTV. Should produce some but not many liquidations.
    assert n >= 0
    assert n < 50  # not all positions


def test_s3_large_drawdown_many_liquidations(state, curve) -> None:
    """A 30% drawdown should trigger massive liquidations."""
    cfg = S3Config(drawdown=0.30, dt_blocks=20, horizon_blocks=30)
    traj = stress_s3(state, cfg, curve)
    n = n_liquidated(traj)
    assert n > 50  # most positions liquidated


def test_s3_monotonic_in_drawdown(state, curve) -> None:
    """Larger drawdown ⇒ at least as many liquidations."""
    last_n = -1
    for d in [0.05, 0.10, 0.15, 0.20, 0.30]:
        cfg = S3Config(drawdown=d, dt_blocks=20, horizon_blocks=30)
        traj = stress_s3(state, cfg, curve)
        n = n_liquidated(traj)
        assert n >= last_n
        last_n = n


def test_s3_bad_debt_grows_with_slippage(state) -> None:
    """A worse slippage curve must produce ≥ bad debt for the same shock."""
    cfg = S3Config(drawdown=0.20, dt_blocks=20, horizon_blocks=30)
    good_curve = SlippageCurve(asset_symbol="WETH", a=1e-5, b=0.4)
    bad_curve = SlippageCurve(asset_symbol="WETH", a=5e-3, b=0.7)

    bd_good = total_bad_debt(stress_s3(state, cfg, good_curve))
    bd_bad = total_bad_debt(stress_s3(state, cfg, bad_curve))
    assert bd_bad >= bd_good


def test_s3_instant_shape_liquidates_at_block_1(state, curve) -> None:
    """Instant shape ⇒ all eligible positions liquidate in the first block."""
    cfg = S3Config(drawdown=0.20, dt_blocks=20, horizon_blocks=20, shape="instant")
    traj = stress_s3(state, cfg, curve)
    # Most liquidations should concentrate at block 1
    cd = cascade_depth(traj)
    n = n_liquidated(traj)
    if n > 0:
        # Cascade depth should be a large fraction of n
        assert cd / n >= 0.5


def test_s3_linear_shape_distributes_liquidations(state, curve) -> None:
    """Linear shape ⇒ liquidations spread over multiple blocks."""
    cfg = S3Config(drawdown=0.20, dt_blocks=50, horizon_blocks=60, shape="linear")
    traj = stress_s3(state, cfg, curve)
    cd = cascade_depth(traj)
    n = n_liquidated(traj)
    if n > 5:
        # Cascade depth should be << n (not all in one block)
        assert cd / n < 0.5


def test_s3_horizon_extends_drawdown(state, curve) -> None:
    """horizon > dt_blocks: price stays at floor; no new liquidations after."""
    cfg = S3Config(drawdown=0.15, dt_blocks=10, horizon_blocks=50)
    traj = stress_s3(state, cfg, curve)
    # After dt_blocks, price is constant; no further liquidations should occur
    early_events = [
        e for e in traj.events if e["kind"] == "liquidation" and e["block"] <= 10 + traj.states[0].block
    ]
    late_events = [
        e for e in traj.events if e["kind"] == "liquidation" and e["block"] > 10 + traj.states[0].block
    ]
    # Late events should be rare (only positions that became liquidatable
    # via interest accrual — possible but small).
    assert len(late_events) <= 0.1 * max(1, len(early_events))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_s3_invalid_drawdown(state, curve) -> None:
    with pytest.raises(ValueError):
        stress_s3(state, S3Config(drawdown=-0.1, dt_blocks=10, horizon_blocks=10), curve)
    with pytest.raises(ValueError):
        stress_s3(state, S3Config(drawdown=1.0, dt_blocks=10, horizon_blocks=10), curve)


def test_s3_invalid_dt_blocks(state, curve) -> None:
    with pytest.raises(ValueError):
        stress_s3(state, S3Config(drawdown=0.1, dt_blocks=0, horizon_blocks=10), curve)


def test_s3_horizon_too_short(state, curve) -> None:
    with pytest.raises(ValueError):
        stress_s3(state, S3Config(drawdown=0.1, dt_blocks=20, horizon_blocks=10), curve)


def test_s3_invariants_preserved(state, curve) -> None:
    """Throughout the trajectory: B <= S, all aggregates non-negative."""
    cfg = S3Config(drawdown=0.20, dt_blocks=20, horizon_blocks=30)
    traj = stress_s3(state, cfg, curve)
    for s in traj.states:
        assert s.total_supply_assets >= -1e-6
        assert s.total_borrow_assets >= -1e-6
        assert s.total_borrow_assets <= s.total_supply_assets + 1e-6


def test_s3_slippage_shortfall_geq_zero(state, curve) -> None:
    cfg = S3Config(drawdown=0.20, dt_blocks=20, horizon_blocks=30)
    traj = stress_s3(state, cfg, curve)
    assert slippage_shortfall(traj) >= 0.0
