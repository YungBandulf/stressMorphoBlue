"""Interest Rate Model — AdaptiveCurveIRM.

Implements the canonical Morpho Blue IRM as deployed on mainnet
(`AdaptiveCurveIRM`). Reference:

    Morpho Labs, *Morpho Blue Whitepaper* §5 (IRM section)
    https://github.com/morpho-org/morpho-blue-irm

The IRM has two outputs at each block:
    - the borrow rate r(U), which is a curve passing through `rate_at_target`
      at `U = U_target`
    - the new `rate_at_target`, which adapts over time toward equilibrium

For our v0 stress framework, we use the *static* curve only — i.e. we accrue
interest using the borrow rate, but freeze `rate_at_target` over the simulation
horizon. The justification is in §3 of this file.

All rates are continuously compounded APR, in 1e0 (so 0.05 = 5%).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from morpho_stress.models.constants import EPS, SECONDS_PER_YEAR


@dataclass(frozen=True, slots=True)
class IrmParams:
    """AdaptiveCurveIRM parameters — see Morpho Labs `AdaptiveCurveIrm.sol`."""

    target_utilization: float = 0.9
    curve_steepness: float = 4.0  # k_d in the whitepaper
    adjustment_speed: float = 50.0  # per year
    initial_rate_at_target: float = 0.04  # 4% APR

    # Bounds (as in Morpho contract)
    min_rate_at_target: float = 0.001  # 0.1% APR
    max_rate_at_target: float = 2.0  # 200% APR


def borrow_rate(utilization: float, rate_at_target: float, params: IrmParams) -> float:
    """Compute the instantaneous borrow APR given current utilization.

    The curve is piecewise:
        - U < U_target: rate = rate_at_target * (1 - (1 - U/U_target) / k_d)
        - U >= U_target: rate = rate_at_target * (1 + (U - U_target) / (1 - U_target) * (k_d - 1))

    This produces a kink at U_target with slope ratio `k_d`.
    """
    u = max(0.0, min(1.0, utilization))
    u_t = params.target_utilization
    k = params.curve_steepness

    if u < u_t:
        # Below target: lower rate, slope = rate_at_target / (k * U_target)
        ratio = (u_t - u) / max(u_t, EPS)
        coeff = 1.0 - ratio / k
    else:
        # Above target: higher rate, slope = rate_at_target * (k-1) / (1 - U_target)
        ratio = (u - u_t) / max(1.0 - u_t, EPS)
        coeff = 1.0 + ratio * (k - 1.0)

    return rate_at_target * coeff


def supply_rate(borrow_apr: float, utilization: float, fee: float) -> float:
    """Effective supplier APR: r_borrow * U * (1 - fee)."""
    return borrow_apr * max(0.0, utilization) * (1.0 - fee)


def accrue(
    total_supply_assets: float,
    total_borrow_assets: float,
    fee: float,
    rate_at_target: float,
    params: IrmParams,
    elapsed_seconds: int,
) -> tuple[float, float]:
    """Accrue interest over `elapsed_seconds`.

    Returns the new (total_supply_assets, total_borrow_assets) after accrual.
    Continuous compounding: ΔB = B * (exp(r_b * Δt / year) - 1).

    Suppliers receive ΔB * (1 - fee); the fee is treated as off-pool (kept
    by the protocol/curator). For v0 we credit suppliers' assets directly.
    """
    if elapsed_seconds <= 0 or total_supply_assets < EPS:
        return total_supply_assets, total_borrow_assets

    u = total_borrow_assets / total_supply_assets if total_supply_assets > EPS else 0.0
    r_b = borrow_rate(u, rate_at_target, params)
    growth = math.expm1(r_b * elapsed_seconds / SECONDS_PER_YEAR)
    interest = total_borrow_assets * growth

    new_borrow = total_borrow_assets + interest
    # Suppliers receive net interest (after fee); fee accrues off-pool.
    new_supply = total_supply_assets + interest * (1.0 - fee)
    return new_supply, new_borrow


# ---------------------------------------------------------------------------
# Justification for static rate_at_target in v0
# ---------------------------------------------------------------------------
#
# Morpho's adaptive mechanism updates rate_at_target with elasticity
# `adjustment_speed` ≈ 50/year, i.e. doubling time ≈ 14 days at full deviation.
# Over a 30-day stress horizon, the adaptive layer would shift rates by tens of
# percent.
#
# However, for *liquidity* stress (our framework's focus), the dominant effect
# of rate moves is on borrower behavior (repay vs hold) — which we model
# explicitly via behavioral rules in the scenarios, not via the rate itself.
# Including the adaptive layer would introduce a second-order coupling that
# obscures the primary stress mechanics.
#
# v1 extension: reactivate the adaptive update and report sensitivity.
