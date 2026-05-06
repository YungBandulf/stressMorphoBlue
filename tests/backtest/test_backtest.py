"""Tests for the backtest module — fixtures, runner, validation criteria."""

from __future__ import annotations

from pathlib import Path

import pytest

from morpho_stress.backtest import (
    BacktestVerdict,
    EventFixture,
    format_verdict,
    list_fixtures,
    load_event,
    run_backtest,
)
from morpho_stress.models.slippage import SlippageCurve


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "data" / "fixtures"


# ---------------------------------------------------------------------------
# Fixture loader
# ---------------------------------------------------------------------------


def test_list_fixtures_finds_all_events() -> None:
    found = list_fixtures(FIXTURES_ROOT)
    assert "kelpdao_2026_04" in found
    assert "usdc_depeg_2023_03" in found
    assert "steth_discount_2022_05" in found


def test_load_kelpdao_fixture() -> None:
    fixture = load_event(FIXTURES_ROOT / "kelpdao_2026_04")
    assert fixture.event_id == "kelpdao_2026_04"
    assert fixture.meta.counterfactual is False
    assert fixture.meta.expected_red_flag is True
    assert "rsETH" in fixture.meta.affected_collaterals

    # Initial state has reasonable values
    assert fixture.initial_state.total_supply_assets == 45_000_000.0
    assert fixture.initial_state.total_borrow_assets == 38_000_000.0
    assert 0.84 < fixture.initial_state.utilization < 0.86

    # Prices CSV has hourly rows over the window
    assert len(fixture.prices) > 200
    assert "market_price_usd" in fixture.prices.columns


def test_load_usdc_fixture() -> None:
    fixture = load_event(FIXTURES_ROOT / "usdc_depeg_2023_03")
    assert fixture.meta.counterfactual is True
    # USDC oracle was sticky — price at snapshot = 1.0
    assert fixture.initial_state.oracle_price == 1.000
    # Verify market price drops to ~0.88 in the window
    assert fixture.market_path.min() < 0.92


def test_load_steth_fixture() -> None:
    fixture = load_event(FIXTURES_ROOT / "steth_discount_2022_05")
    assert fixture.meta.counterfactual is True
    # stETH ~$2050 at start, drops to ~$1925 (ratio 0.94)
    assert fixture.market_path.max() > 1900
    assert fixture.market_path.min() < 1980


def test_load_event_missing_dir() -> None:
    with pytest.raises(FileNotFoundError):
        load_event(FIXTURES_ROOT / "nonexistent_event_99")


def test_t0_index_in_window() -> None:
    fixture = load_event(FIXTURES_ROOT / "kelpdao_2026_04")
    idx = fixture.t0_index()
    assert 0 < idx < len(fixture.prices)
    # T0 should be before the event timestamp
    ts = fixture.price_timestamps[idx]
    assert ts <= fixture.meta.event_ts


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@pytest.fixture
def slippage_curve_lrt():
    """Conservative slippage curve representative of LRT collateral."""
    return SlippageCurve(asset_symbol="rsETH", a=5e-4, b=0.6)


@pytest.fixture
def slippage_curve_stable():
    """Tight slippage curve for stable-on-stable swaps."""
    return SlippageCurve(asset_symbol="USDC", a=1e-5, b=0.4)


def test_run_backtest_returns_verdict(slippage_curve_lrt) -> None:
    fixture = load_event(FIXTURES_ROOT / "kelpdao_2026_04")
    verdict = run_backtest(fixture, slippage_curve_lrt, n_mc_paths=20)
    assert isinstance(verdict, BacktestVerdict)
    assert verdict.event_id == "kelpdao_2026_04"
    assert verdict.severity_flag in {"green", "yellow", "red"}
    assert len(verdict.criteria) == 3


def test_kelpdao_should_be_flagged(slippage_curve_lrt) -> None:
    """KelpDAO is the primary anchor; framework MUST flag it."""
    fixture = load_event(FIXTURES_ROOT / "kelpdao_2026_04")
    verdict = run_backtest(fixture, slippage_curve_lrt, n_mc_paths=50)
    assert verdict.framework_flagged, (
        f"Framework failed to flag KelpDAO. Verdict:\n{format_verdict(verdict)}"
    )
    assert verdict.severity_flag in {"yellow", "red"}


def test_format_verdict_runs_without_error(slippage_curve_lrt) -> None:
    fixture = load_event(FIXTURES_ROOT / "kelpdao_2026_04")
    verdict = run_backtest(fixture, slippage_curve_lrt, n_mc_paths=10)
    text = format_verdict(verdict)
    assert "kelpdao_2026_04" in text
    assert "criteria:" in text


def test_metrics_populated(slippage_curve_lrt) -> None:
    fixture = load_event(FIXTURES_ROOT / "kelpdao_2026_04")
    verdict = run_backtest(fixture, slippage_curve_lrt, n_mc_paths=20)
    assert "LCR_onchain_v03" in verdict.metrics
    assert "time_to_illiquid_hours" in verdict.metrics
    assert "P_bad_debt_gt_0" in verdict.metrics
    # All metrics should be finite
    for k, v in verdict.metrics.items():
        if v == float("inf"):
            continue  # TTI can be inf if never illiquid
        assert v == v, f"{k} is NaN"  # NaN check
