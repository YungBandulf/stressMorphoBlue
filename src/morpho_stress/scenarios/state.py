"""Market state representation — the formal state vector x(M, t).

Implementation of the notation from `docs/SCENARIOS.md §1`. The `MarketState`
dataclass is the single in-memory representation passed through the simulation
pipeline. It is immutable; every block transition produces a new state.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Self

import numpy as np

from morpho_stress.models.constants import EPS


@dataclass(frozen=True, slots=True)
class Position:
    """A single borrower position in a market.

    Attributes are denominated in their natural units (collateral asset for
    `collateral`, loan asset for `borrow_*`).

    Notes:
        We track shares as the canonical state and derive assets via the
        market's borrow index. This matches Morpho Blue's on-chain accounting.
    """

    borrower: str
    collateral: float
    borrow_shares: float

    def borrow_assets(self, total_borrow_assets: float, total_borrow_shares: float) -> float:
        """Convert shares to assets using current borrow index."""
        if total_borrow_shares < EPS:
            return 0.0
        return self.borrow_shares * total_borrow_assets / total_borrow_shares

    def ltv(
        self,
        total_borrow_assets: float,
        total_borrow_shares: float,
        oracle_price: float,
    ) -> float:
        """Loan-to-value: borrow / (collateral × price). Returns +inf if collateral is 0."""
        b = self.borrow_assets(total_borrow_assets, total_borrow_shares)
        denom = self.collateral * oracle_price
        if denom < EPS:
            return float("inf") if b > 0 else 0.0
        return b / denom


@dataclass(frozen=True, slots=True)
class MarketParams:
    """Immutable Morpho Blue market parameters."""

    market_id: str
    loan_decimals: int
    collateral_decimals: int
    lltv: float
    fee: float

    # IRM parameters (AdaptiveCurveIRM defaults — see Morpho Labs spec)
    irm_target_utilization: float = 0.9
    irm_curve_steepness: float = 4.0
    irm_adjustment_speed: float = 50.0  # per year
    irm_initial_rate_at_target: float = 0.04  # 4% APR

    # Oracle config (read at market level)
    oracle_kind: str = "chainlink"


@dataclass(frozen=True, slots=True)
class MarketState:
    """State vector for a Morpho Blue market at a given block.

    Maps to ``x(M, t) = (S, B, L, U, C, P, {(b_i, c_i)}, {s_j})`` from
    `docs/SCENARIOS.md §1.1`.
    """

    params: MarketParams
    block: int
    block_ts: int  # unix seconds
    total_supply_assets: float
    total_supply_shares: float
    total_borrow_assets: float
    total_borrow_shares: float
    total_collateral: float
    oracle_price: float
    rate_at_target: float
    positions: tuple[Position, ...] = field(default_factory=tuple)
    queued_withdrawals: float = 0.0  # accumulator for S1 unhonored withdrawals
    realized_bad_debt: float = 0.0  # cumulative bad debt over scenario

    # ----- Derived quantities -----

    @property
    def liquidity(self) -> float:
        """L_t = S_t - B_t."""
        return max(0.0, self.total_supply_assets - self.total_borrow_assets)

    @property
    def utilization(self) -> float:
        """U_t = B_t / S_t in [0, 1]."""
        if self.total_supply_assets < EPS:
            return 0.0
        return self.total_borrow_assets / self.total_supply_assets

    def liquidatable_positions(self) -> tuple[Position, ...]:
        """Positions with LTV > LLTV at current oracle price."""
        return tuple(
            p
            for p in self.positions
            if p.ltv(self.total_borrow_assets, self.total_borrow_shares, self.oracle_price)
            > self.params.lltv
        )

    # ----- Mutators (return new state) -----

    def replace(self, **kwargs: object) -> Self:
        """Return a new state with selected fields replaced."""
        return replace(self, **kwargs)

    def to_dict(self) -> dict[str, float]:
        """Flat snapshot for logging / serialization."""
        return {
            "block": float(self.block),
            "S": self.total_supply_assets,
            "B": self.total_borrow_assets,
            "L": self.liquidity,
            "U": self.utilization,
            "C": self.total_collateral,
            "P": self.oracle_price,
            "queued": self.queued_withdrawals,
            "bad_debt": self.realized_bad_debt,
            "n_positions": float(len(self.positions)),
        }


def assert_invariants(state: MarketState) -> None:
    """Validate state invariants. Raises AssertionError on violation.

    Used in tests and as a smoke check during development.
    """
    assert state.total_supply_assets >= -EPS, "negative supply"
    assert state.total_borrow_assets >= -EPS, "negative borrow"
    assert (
        state.total_borrow_assets <= state.total_supply_assets + EPS
    ), f"over-borrow: B={state.total_borrow_assets} > S={state.total_supply_assets}"
    assert state.total_collateral >= -EPS, "negative collateral"
    assert state.oracle_price > 0, "non-positive oracle price"
    assert 0 <= state.params.lltv <= 1, "lltv out of range"
    # Aggregate position collateral consistency (allow small drift from share rounding)
    sum_pos_collateral = sum(p.collateral for p in state.positions)
    drift = abs(sum_pos_collateral - state.total_collateral)
    assert drift < max(1.0, 1e-6 * state.total_collateral), (
        f"position collateral sum {sum_pos_collateral} drifts from "
        f"total {state.total_collateral} by {drift}"
    )
    sum_pos_shares = sum(p.borrow_shares for p in state.positions)
    share_drift = abs(sum_pos_shares - state.total_borrow_shares)
    assert share_drift < max(1.0, 1e-6 * max(state.total_borrow_shares, 1.0)), (
        f"position shares sum {sum_pos_shares} drifts from "
        f"total {state.total_borrow_shares} by {share_drift}"
    )


def total_borrow_assets_from_positions(
    positions: tuple[Position, ...],
    total_borrow_assets: float,
    total_borrow_shares: float,
) -> float:
    """Reconstruct B from positions (for invariant checks)."""
    if total_borrow_shares < EPS:
        return 0.0
    return float(
        np.sum([p.borrow_assets(total_borrow_assets, total_borrow_shares) for p in positions])
    )
