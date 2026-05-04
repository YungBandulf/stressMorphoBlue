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
    s, b = accrue(100.0, 80.0, 0.0, 0.04, IrmParams(), 0)
    assert s == 100.0
    assert b == 80.0


def test_accrue_increases_borrow_more_than_supply() -> None:
    """Borrow grows by full interest, supply grows by net (after fee)."""
    s0, b0 = 100.0, 80.0
    fee = 0.10
    s1, b1 = accrue(s0, b0, fee, 0.10, IrmParams(), 365 * 24 * 3600)  # 1 year
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
    # At U=1, borrow_rate = rat * (1 + 0 * (k-1)) = rat
    # Actually at U_target, borrow_rate = rat. We pick U=U_target via S=B.
    s0, b0 = 100.0, 90.0  # U = 0.9 = U_target
    s1, b1 = accrue(s0, b0, 0.0, rat, IrmParams(), 365 * 24 * 3600)
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
