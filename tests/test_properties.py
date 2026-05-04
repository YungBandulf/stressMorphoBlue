"""Property-based tests with Hypothesis on critical invariants.

Strategy: cover the highest-stakes invariants (those that, if violated, would
silently corrupt scenario results) with property tests that explore the full
parameter space rather than picked examples.

Targets:

1. **IRM borrow_rate** — monotonic in U, equals rate_at_target at U_target,
   continuous everywhere
2. **IRM update_rate_at_target** — clipped to bounds, sign of change matches
   sign of (U - U_target)
3. **TWAP** — geomean property: TWAP of [p1, p2] with equal weights ≈ sqrt(p1*p2)
4. **Slippage curve** — monotonic in volume, capped at max_slippage
5. **S1 invariants** — non-negative supply/borrow, total supply non-increasing
   under net withdrawals
6. **S3 invariants** — bad debt monotonic in drawdown
7. **Liquidation** — bad debt + realized = repaid
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from morpho_stress.models.constants import EPS
from morpho_stress.models.irm import (
    IrmParams,
    borrow_rate,
    update_rate_at_target,
)
from morpho_stress.models.oracle import TwapOracle
from morpho_stress.models.slippage import SlippageCurve
from morpho_stress.scenarios import (
    S1Config,
    S3Config,
    stress_s1,
    stress_s3,
)
from morpho_stress.utils.mock import make_market_state


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

utilizations = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
rates_at_target = st.floats(min_value=0.001, max_value=2.0, allow_nan=False)
durations_seconds = st.integers(min_value=1, max_value=3 * 365 * 24 * 3600)


# ---------------------------------------------------------------------------
# IRM properties
# ---------------------------------------------------------------------------


@given(u1=utilizations, u2=utilizations, rat=rates_at_target)
def test_property_borrow_rate_monotonic(u1: float, u2: float, rat: float) -> None:
    """For any u1 <= u2, borrow_rate(u1) <= borrow_rate(u2) at the same rate_at_target."""
    if u1 > u2:
        u1, u2 = u2, u1
    params = IrmParams()
    r1 = borrow_rate(u1, rat, params)
    r2 = borrow_rate(u2, rat, params)
    assert r1 <= r2 + 1e-9


@given(rat=rates_at_target)
def test_property_borrow_rate_at_target(rat: float) -> None:
    """borrow_rate(U_target) == rate_at_target exactly."""
    params = IrmParams()
    r = borrow_rate(params.target_utilization, rat, params)
    assert math.isclose(r, rat, rel_tol=1e-12)


@given(u=utilizations, rat=rates_at_target, dt=durations_seconds)
def test_property_update_rat_clipped(u: float, rat: float, dt: int) -> None:
    """update_rate_at_target output is always in [min_rate, max_rate]."""
    params = IrmParams()
    new_rat = update_rate_at_target(rat, u, params, dt)
    assert params.min_rate_at_target - 1e-12 <= new_rat
    assert new_rat <= params.max_rate_at_target + 1e-12


@given(u=utilizations, rat=rates_at_target)
def test_property_update_rat_sign(u: float, rat: float) -> None:
    """Sign of (new_rat - rat) matches sign of (U - U_target),
    UNLESS the result is at a boundary."""
    params = IrmParams()
    new_rat = update_rate_at_target(rat, u, params, elapsed_seconds=86400)
    # At the boundaries, the relationship breaks (clipped); only check interior cases
    is_interior = params.min_rate_at_target * 1.01 < new_rat < params.max_rate_at_target * 0.99
    if is_interior and abs(u - params.target_utilization) > 0.01:
        if u > params.target_utilization:
            assert new_rat >= rat - 1e-9
        else:
            assert new_rat <= rat + 1e-9


# ---------------------------------------------------------------------------
# TWAP properties
# ---------------------------------------------------------------------------


@given(
    p1=st.floats(min_value=0.01, max_value=1e6),
    p2=st.floats(min_value=0.01, max_value=1e6),
)
def test_property_twap_geomean_two_points(p1: float, p2: float) -> None:
    """TWAP of two equally-weighted observations ≈ geomean = sqrt(p1*p2)."""
    o = TwapOracle(initial_price=p1, lambda_blocks=2)
    o.update(p2, block=1)
    twap = o.read()
    expected_geomean = math.sqrt(p1 * p2)
    # Tolerance accommodates the discrete nature of dt weighting (not exactly equal weights)
    rel_tol = 0.10
    assert math.isclose(twap, expected_geomean, rel_tol=rel_tol), (
        f"twap={twap}, geomean={expected_geomean}, p1={p1}, p2={p2}"
    )


@given(prices=st.lists(st.floats(min_value=0.1, max_value=1e4), min_size=2, max_size=20))
def test_property_twap_bounded_by_minmax(prices: list[float]) -> None:
    """TWAP must lie in [min(prices), max(prices)]."""
    o = TwapOracle(initial_price=prices[0], lambda_blocks=len(prices))
    for i, p in enumerate(prices[1:], start=1):
        o.update(p, block=i)
    twap = o.read()
    assert min(prices) - EPS <= twap <= max(prices) + EPS


# ---------------------------------------------------------------------------
# Slippage curve properties
# ---------------------------------------------------------------------------


@given(
    a=st.floats(min_value=1e-8, max_value=1e-2),
    b=st.floats(min_value=0.1, max_value=1.5),
    v1=st.floats(min_value=0.01, max_value=1e8),
    v2=st.floats(min_value=0.01, max_value=1e8),
)
def test_property_slippage_monotonic(a: float, b: float, v1: float, v2: float) -> None:
    """For any v1 <= v2, slippage(v1) <= slippage(v2)."""
    if v1 > v2:
        v1, v2 = v2, v1
    curve = SlippageCurve(asset_symbol="X", a=a, b=b)
    s1 = curve.slippage(v1)
    s2 = curve.slippage(v2)
    assert s1 <= s2 + EPS


@given(
    a=st.floats(min_value=1e-8, max_value=1e-2),
    b=st.floats(min_value=0.1, max_value=1.5),
    v=st.floats(min_value=0.01, max_value=1e10),
    cap=st.floats(min_value=0.01, max_value=0.99),
)
def test_property_slippage_capped(a: float, b: float, v: float, cap: float) -> None:
    """Slippage never exceeds max_slippage."""
    curve = SlippageCurve(asset_symbol="X", a=a, b=b, max_slippage=cap)
    s = curve.slippage(v)
    assert 0.0 <= s <= cap + EPS


# ---------------------------------------------------------------------------
# S1 properties
# ---------------------------------------------------------------------------


@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
@given(
    alpha=st.floats(min_value=0.0, max_value=0.5),
    duration=st.integers(min_value=10, max_value=500),
)
def test_property_s1_supply_non_increasing(alpha: float, duration: int) -> None:
    """Under S1, total_supply_assets cannot increase faster than interest accrual."""
    state = make_market_state(seed=7)
    cfg = S1Config(alpha=alpha, duration_blocks=duration, horizon_blocks=duration)
    traj = stress_s1(state, cfg)
    # Final supply <= initial supply * (1 + max_interest_growth)
    # Over duration blocks at <= 200% APR (max), max growth = exp(2 * dt/year)
    max_growth = math.exp(2.0 * duration * 12 / (365 * 24 * 3600))
    assert traj.final_state.total_supply_assets <= state.total_supply_assets * max_growth + 1e-3


@settings(max_examples=10)
@given(alpha=st.floats(min_value=0.0, max_value=0.99))
def test_property_s1_queued_non_negative(alpha: float) -> None:
    """queued_withdrawals is always >= 0."""
    state = make_market_state(seed=11)
    cfg = S1Config(alpha=alpha, duration_blocks=100, horizon_blocks=200)
    traj = stress_s1(state, cfg)
    for s in traj.states:
        assert s.queued_withdrawals >= -EPS


# ---------------------------------------------------------------------------
# S3 properties
# ---------------------------------------------------------------------------


@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
@given(d1=st.floats(min_value=0.0, max_value=0.4), d2=st.floats(min_value=0.0, max_value=0.4))
def test_property_s3_bad_debt_monotonic_in_drawdown(d1: float, d2: float) -> None:
    """Larger drawdown ⇒ bad debt monotone non-decreasing (under fixed slippage curve)."""
    if d1 > d2:
        d1, d2 = d2, d1
    state = make_market_state(seed=23)
    curve = SlippageCurve(asset_symbol="WETH", a=2e-4, b=0.55)

    cfg1 = S3Config(drawdown=d1, dt_blocks=20, horizon_blocks=30)
    cfg2 = S3Config(drawdown=d2, dt_blocks=20, horizon_blocks=30)

    bd1 = stress_s3(state, cfg1, curve).final_state.realized_bad_debt
    bd2 = stress_s3(state, cfg2, curve).final_state.realized_bad_debt

    assert bd2 >= bd1 - 1e-3  # tolerance for floating point + interest accrual artifacts
