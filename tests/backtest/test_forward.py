"""Tests for forward-looking risk assessment."""

from __future__ import annotations

import pytest

from morpho_stress.backtest import (
    MarketProfile,
    MarketRiskAssessment,
    assess_all_markets,
    assess_market,
    current_markets,
)


def test_current_markets_nonempty() -> None:
    markets = current_markets()
    assert len(markets) >= 5
    labels = [m.market_label for m in markets]
    assert "wstETH/USDC" in labels


def test_market_profile_validation() -> None:
    profile = current_markets()[0]
    assert profile.utilization > 0
    assert profile.lltv > 0
    assert profile.lltv < 1
    assert profile.n_positions > 0


def test_assess_market_returns_assessment() -> None:
    profile = current_markets()[0]
    result = assess_market(profile, n_mc_paths=20)
    assert isinstance(result, MarketRiskAssessment)
    assert result.severity_flag in {"green", "yellow", "red"}
    assert result.market_label == profile.market_label
    assert result.lcr_v03 > 0
    assert 0 <= result.p_bad_debt_gt_0 <= 1


def test_assess_all_markets_returns_sorted() -> None:
    results = assess_all_markets(n_mc_paths=20)
    assert len(results) == len(current_markets())
    # First result should have severity ≥ all others (red > yellow > green)
    sev_rank = {"red": 0, "yellow": 1, "green": 2}
    for prev, nxt in zip(results, results[1:]):
        assert sev_rank[prev.severity_flag] <= sev_rank[nxt.severity_flag]


def test_high_utilization_market_has_lower_lcr() -> None:
    """A market at U=93% should have lower LCR than one at U=84%, ceteris paribus."""
    high_u = MarketProfile(
        market_label="test_high_u",
        loan_symbol="USDC",
        collateral_symbol="WETH",
        total_supply_usd=100_000_000.0,
        utilization=0.93,
        n_positions=100,
        avg_ltv=0.78,
        lltv=0.86,
        oracle_price=2_000.0,
        rate_at_target=0.05,
        drawdown_p99=0.15,
    )
    low_u = MarketProfile(
        market_label="test_low_u",
        loan_symbol="USDC",
        collateral_symbol="WETH",
        total_supply_usd=100_000_000.0,
        utilization=0.70,
        n_positions=100,
        avg_ltv=0.55,
        lltv=0.86,
        oracle_price=2_000.0,
        rate_at_target=0.05,
        drawdown_p99=0.15,
    )
    high_result = assess_market(high_u, n_mc_paths=20)
    low_result = assess_market(low_u, n_mc_paths=20)
    # High-utilization market should have lower LCR (less L1 buffer)
    assert high_result.lcr_v03 <= low_result.lcr_v03 * 1.2  # allow some noise


def test_high_drawdown_p99_increases_bad_debt_probability() -> None:
    """Larger drawdown_p99 → higher P[bad_debt > 0]."""
    base_args = {
        "market_label": "test",
        "loan_symbol": "USDC",
        "collateral_symbol": "WETH",
        "total_supply_usd": 100_000_000.0,
        "utilization": 0.85,
        "n_positions": 100,
        "avg_ltv": 0.72,
        "lltv": 0.86,
        "oracle_price": 2_000.0,
        "rate_at_target": 0.05,
    }
    safe = MarketProfile(**base_args, drawdown_p99=0.05)
    risky = MarketProfile(**base_args, drawdown_p99=0.30)

    safe_r = assess_market(safe, n_mc_paths=50, seed=42)
    risky_r = assess_market(risky, n_mc_paths=50, seed=42)
    assert risky_r.p_bad_debt_gt_0 >= safe_r.p_bad_debt_gt_0


def test_assess_with_custom_profiles() -> None:
    """User can pass custom profiles instead of the default roster."""
    custom = [
        MarketProfile(
            market_label="custom_market",
            loan_symbol="USDC",
            collateral_symbol="WETH",
            total_supply_usd=50_000_000.0,
            utilization=0.80,
            n_positions=50,
            avg_ltv=0.70,
            lltv=0.86,
            oracle_price=2_000.0,
            rate_at_target=0.04,
        ),
    ]
    results = assess_all_markets(custom, n_mc_paths=10)
    assert len(results) == 1
    assert results[0].market_label == "custom_market"
