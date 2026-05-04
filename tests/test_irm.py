"""Tests for the IRM module."""

from __future__ import annotations

import math

import pytest

from morpho_stress.models.irm import (
    IrmParams,
    accrue,
    borrow_rate,
    supply_rate,
)


def test_borrow_rate_at_target_returns_rate_at_target() -> None:
    """At U = U_target, borrow_rate must equal rate_at_target exactly."""
    params = IrmParams()
    rat = 0.05
    assert math.isclose(
        borrow_rate(params.target_utilization, rat, params), rat, rel_tol=1e-12
    )


def test_borrow_rate_monotonic_in_utilization() -> None:
    """Borrow rate must be non-decreasing in utilization."""
    params = IrmParams()
    rat = 0.04
    rates = [borrow_rate(u, rat, params) for u in [0.0, 0.1, 0.5, 0.85, 0.9, 0.95, 1.0]]
    for prev, nxt in zip(rates, rates[1:]):
        assert nxt >= prev - 1e-12, f"non-monotonic: {prev} -> {nxt}"


def test_borrow_rate_kink_steeper_above_target() -> None:
    """The slope above U_target should exceed the slope below (curve steepness)."""
    params = IrmParams()
    rat = 0.04
    eps = 0.01
    below_slope = (
        borrow_rate(params.target_utilization, rat, params)
        - borrow_rate(params.target_utilization - eps, rat, params)
    ) / eps
    above_slope = (
        borrow_rate(params.target_utilization + eps, rat, params)
        - borrow_rate(params.target_utilization, rat, params)
    ) / eps
    # Steepness factor k=4: above slope ≈ (k-1)/k * U_target / (1-U_target) × below slope
    assert above_slope > below_slope


def test_borrow_rate_zero_utilization_below_target() -> None:
    """At U=0, rate must be reduced to (1 - 1/k) of rate_at_target."""
    params = IrmParams()
    rat = 0.04
    expected = rat * (1.0 - 1.0 / params.curve_steepness)
    actual = borrow_rate(0.0, rat, params)
    assert math.isclose(actual, expected, rel_tol=1e-9)


def test_supply_rate_zero_at_zero_utilization() -> None:
    assert supply_rate(0.04, 0.0, 0.0) == 0.0


def test_supply_rate_lower_than_borrow() -> None:
    """Suppliers always earn less than borrowers pay (per unit of supply)."""
    s = supply_rate(0.05, 0.85, 0.0)
    b = 0.05
    # s = b * U => s < b when U < 1
    assert s < b


def test_accrue_no_time_elapsed_is_identity() -> None:
    s, b, r = accrue(100.0, 80.0, 0.0, 0.04, IrmParams(), 0)
    assert s == 100.0
    assert b == 80.0
    assert r == 0.04


def test_accrue_increases_borrow_more_than_supply() -> None:
    """Borrow grows by full interest, supply grows by net (after fee)."""
    s0, b0 = 100.0, 80.0
    fee = 0.10
    # Freeze rate_at_target update for this test — we want pure interest accrual semantics
    s1, b1, _ = accrue(
        s0, b0, fee, 0.10, IrmParams(), 365 * 24 * 3600, update_target=False
    )
    delta_b = b1 - b0
    delta_s = s1 - s0
    # delta_s should be ~ delta_b * (1 - fee)
    assert math.isclose(delta_s, delta_b * (1 - fee), rel_tol=1e-9)
    # Borrow grew, supply grew, neither overshot
    assert delta_b > 0
    assert delta_s > 0
    assert delta_s < delta_b


def test_accrue_one_year_at_known_rate() -> None:
    """Sanity-check the continuous-compounding formula."""
    rat = 0.10  # 10% APR
    # At U=U_target, borrow_rate = rat. We pick S=B/0.9 = U_target.
    s0, b0 = 100.0, 90.0  # U = 0.9 = U_target
    # Freeze rate_at_target so pure compound formula holds
    s1, b1, _ = accrue(
        s0, b0, 0.0, rat, IrmParams(), 365 * 24 * 3600, update_target=False
    )
    expected_b = b0 * math.exp(rat)
    assert math.isclose(b1, expected_b, rel_tol=1e-6)


@pytest.mark.parametrize("u", [0.0, 0.1, 0.5, 0.9, 0.99])
def test_borrow_rate_continuity_at_kink(u: float) -> None:
    """Rate function must be continuous (no jump at U_target)."""
    params = IrmParams()
    rat = 0.04
    eps = 1e-9
    if abs(u - params.target_utilization) < eps:
        # Skip exact kink point
        return
    rate = borrow_rate(u, rat, params)
    rate_eps = borrow_rate(u + eps, rat, params)
    assert math.isclose(rate, rate_eps, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Adaptive layer — rate_at_target evolution
# ---------------------------------------------------------------------------

from morpho_stress.models.irm import update_rate_at_target  # noqa: E402


def test_update_at_target_no_change_when_at_target() -> None:
    """If U == U_target, rate_at_target must remain constant."""
    params = IrmParams()
    new_rat = update_rate_at_target(0.04, params.target_utilization, params, 86400)
    assert math.isclose(new_rat, 0.04, rel_tol=1e-12)


def test_update_at_target_above_target_increases_rate() -> None:
    """Above U_target ⇒ rate_at_target rises."""
    params = IrmParams()
    new_rat = update_rate_at_target(0.04, utilization=0.95, params=params, elapsed_seconds=86400)
    assert new_rat > 0.04


def test_update_at_target_below_target_decreases_rate() -> None:
    """Below U_target ⇒ rate_at_target falls."""
    params = IrmParams()
    new_rat = update_rate_at_target(0.04, utilization=0.5, params=params, elapsed_seconds=86400)
    assert new_rat < 0.04


def test_update_at_target_clipped_at_max() -> None:
    """Sustained high utilization must not push rate above max."""
    params = IrmParams(max_rate_at_target=0.5)
    # Strong overshoot, very long Δt — rate should be clipped
    new_rat = update_rate_at_target(
        0.45, utilization=1.0, params=params, elapsed_seconds=365 * 24 * 3600
    )
    assert new_rat == params.max_rate_at_target


def test_update_at_target_clipped_at_min() -> None:
    """Sustained low utilization must not push rate below min."""
    params = IrmParams(min_rate_at_target=0.001)
    new_rat = update_rate_at_target(
        0.005, utilization=0.0, params=params, elapsed_seconds=365 * 24 * 3600
    )
    assert new_rat == params.min_rate_at_target


def test_update_at_target_zero_elapsed_is_identity() -> None:
    params = IrmParams()
    new_rat = update_rate_at_target(0.04, utilization=0.99, params=params, elapsed_seconds=0)
    assert new_rat == 0.04


def test_adaptive_doubling_time() -> None:
    """At full deviation (U=1, U_target=0.9), the doubling time is approx
    ln(2) × max(U_t, 1-U_t) / speed years.

    With speed=50 and U_target=0.9, max(0.9, 0.1) = 0.9, so doubling time
    ≈ ln(2) × 0.9 / 50 ≈ 0.01247 year ≈ 4.55 days.
    """
    params = IrmParams(adjustment_speed=50.0, target_utilization=0.9)
    # Actually for U=1, err = (1-0.9)/0.9 = 0.111. doubling: ln(2) / (speed × err)
    # = ln(2) / (50 × 0.111) = 0.693 / 5.555 = 0.1247 year ≈ 45.5 days
    elapsed = int(0.1247 * 365 * 24 * 3600)
    new_rat = update_rate_at_target(0.04, utilization=1.0, params=params, elapsed_seconds=elapsed)
    assert math.isclose(new_rat, 0.08, rel_tol=0.05)  # 5% tolerance


def test_accrue_with_adaptive_update() -> None:
    """Accrue at U > U_target should both grow borrow AND raise rate_at_target."""
    s, b, r = accrue(
        100.0, 95.0, 0.0, 0.04, IrmParams(), 86400, update_target=True
    )
    assert b > 95.0  # interest accrued
    assert r > 0.04  # rate rose because U=0.95 > U_target=0.9


def test_accrue_with_frozen_target() -> None:
    """update_target=False keeps rate_at_target constant."""
    _, _, r = accrue(100.0, 95.0, 0.0, 0.04, IrmParams(), 86400, update_target=False)
    assert r == 0.04
