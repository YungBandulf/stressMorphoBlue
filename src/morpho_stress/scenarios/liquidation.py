"""Liquidation engine.

Implements Morpho Blue's liquidation logic as deployed on-chain, simplified
to the level of detail needed for our liquidity stress framework:

1. A position is liquidatable iff its LTV exceeds the market's LLTV.
2. The liquidator repays a portion of the borrower's debt and seizes
   collateral with an incentive multiplier (LIF).
3. The seized collateral is sold on a DEX, with realized price discounted by
   the slippage curve `π(C, V)`.
4. If the recovered loan asset is less than the repaid debt, the difference is
   bad debt — the supplier pool absorbs the loss.

Reference:
    - Morpho Labs, Morpho Blue Whitepaper §6 (Liquidations)
    - On-chain: `Morpho.liquidate(MarketParams, borrower, seizedAssets, repaidShares, data)`

Simplifications vs on-chain:
    - No callback (no MEV / flashloan-funded liquidator modeling)
    - Liquidations are immediate within the block (no mempool delay)
    - Liquidator always liquidates the maximum allowed amount (close factor = 1)
"""

from __future__ import annotations

from dataclasses import dataclass

from morpho_stress.models.constants import EPS
from morpho_stress.models.slippage import SlippageCurve
from morpho_stress.scenarios.state import MarketState, Position


@dataclass(frozen=True, slots=True)
class LiquidationOutcome:
    """Result of a single position's liquidation."""

    borrower: str
    repaid_assets: float  # loan asset paid back
    repaid_shares: float
    seized_collateral: float
    realized_loan_value: float  # what the liquidator gets after DEX sale
    bad_debt_assets: float  # max(0, repaid_assets - realized_loan_value)


def liquidation_incentive_factor(lltv: float) -> float:
    """Morpho Blue's LIF formula.

    LIF = min(M, 1 / (β * LLTV + (1 - β)))
    where β = 0.3, M = 1.15

    For LLTV = 0.86, LIF ≈ 1.043 (the canonical 4.3% bonus).
    """
    beta = 0.3
    m_cap = 1.15
    return min(m_cap, 1.0 / (beta * lltv + (1.0 - beta)))


def liquidate_position(
    state: MarketState,
    position: Position,
    market_price: float,
    slippage_curve: SlippageCurve,
) -> tuple[LiquidationOutcome, MarketState]:
    """Liquidate a single position fully and return updated state.

    The liquidator:
        1. Repays `position.borrow_assets` worth of loan
        2. Seizes `position.collateral × LIF / oracle_price` worth (capped at
           `position.collateral`)
        3. Sells seized collateral on DEX at `market_price × (1 - π)`
        4. Bad debt = repaid - realized

    Args:
        state: current market state
        position: the position to liquidate (assumed liquidatable)
        market_price: external/DEX market price (≠ oracle price under stress)
        slippage_curve: π(V) for this collateral

    Returns:
        (outcome, new_state) — outcome is the trade detail; new_state has the
        position removed and totals updated.
    """
    # Amount of loan being cleared, in assets
    repaid_assets = position.borrow_assets(
        state.total_borrow_assets, state.total_borrow_shares
    )
    repaid_shares = position.borrow_shares

    if repaid_assets < EPS:
        # Nothing to liquidate — position has zero debt
        new_state = state.replace(
            positions=tuple(p for p in state.positions if p.borrower != position.borrower)
        )
        return (
            LiquidationOutcome(
                borrower=position.borrower,
                repaid_assets=0.0,
                repaid_shares=0.0,
                seized_collateral=0.0,
                realized_loan_value=0.0,
                bad_debt_assets=0.0,
            ),
            new_state,
        )

    lif = liquidation_incentive_factor(state.params.lltv)
    # Collateral the liquidator wants to seize (in collateral units), capped at position
    desired_seize = repaid_assets * lif / state.oracle_price
    seized = min(desired_seize, position.collateral)

    # Realized value of seized collateral when sold on DEX
    realized_price = slippage_curve.realized_price(seized, market_price)
    realized_loan_value = seized * realized_price

    bad_debt = max(0.0, repaid_assets - realized_loan_value)

    # State update:
    #   - remove the position
    #   - reduce total_borrow_assets by repaid (assets) and shares by repaid_shares
    #   - reduce total_collateral by seized
    #   - if bad_debt > 0, the supplier pool absorbs: total_supply_assets is
    #     reduced by bad_debt (proportional socialization)
    new_positions = tuple(p for p in state.positions if p.borrower != position.borrower)
    new_borrow_assets = max(0.0, state.total_borrow_assets - repaid_assets)
    new_borrow_shares = max(0.0, state.total_borrow_shares - repaid_shares)
    new_collateral = max(0.0, state.total_collateral - seized)
    new_supply_assets = max(0.0, state.total_supply_assets - bad_debt)

    new_state = state.replace(
        positions=new_positions,
        total_borrow_assets=new_borrow_assets,
        total_borrow_shares=new_borrow_shares,
        total_collateral=new_collateral,
        total_supply_assets=new_supply_assets,
        realized_bad_debt=state.realized_bad_debt + bad_debt,
    )

    return (
        LiquidationOutcome(
            borrower=position.borrower,
            repaid_assets=repaid_assets,
            repaid_shares=repaid_shares,
            seized_collateral=seized,
            realized_loan_value=realized_loan_value,
            bad_debt_assets=bad_debt,
        ),
        new_state,
    )


def liquidate_all_eligible(
    state: MarketState,
    market_price: float,
    slippage_curve: SlippageCurve,
) -> tuple[list[LiquidationOutcome], MarketState]:
    """Liquidate every liquidatable position at the current oracle price.

    The DEX impact of *aggregate* selling is computed once on the total
    seized volume — this matters under endogenous regimes (S4) where the
    cumulative impact is what moves the oracle.
    """
    eligible = state.liquidatable_positions()
    if not eligible:
        return [], state

    # Compute aggregate seized volume *before* slippage to size the DEX impact
    # with the actual realized seize per position.
    outcomes: list[LiquidationOutcome] = []
    new_state = state
    for pos in eligible:
        outcome, new_state = liquidate_position(
            new_state, pos, market_price, slippage_curve
        )
        outcomes.append(outcome)

    return outcomes, new_state
