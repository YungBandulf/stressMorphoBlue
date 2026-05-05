"""Phase 5 demo — full pipeline.

1. Re-run backtest with v0.3 framework (LCR refactored, alpha event-calibrated)
2. Demonstrate slippage-curve fitting from synthetic Uniswap V3 swaps
3. Forward-looking risk assessment on top-5 representative markets

Usage:
    PYTHONPATH=src python notebooks/phase5_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from morpho_stress.backtest import (  # noqa: E402
    assess_all_markets,
    current_markets,
    fit_with_diagnostics,
    format_verdict,
    list_fixtures,
    load_event,
    run_backtest,
    synthesize_uniswap_swaps,
)
from morpho_stress.models.slippage import SlippageCurve  # noqa: E402


SLIPPAGE_CURVES = {
    "rsETH": SlippageCurve(asset_symbol="rsETH", a=5e-4, b=0.60, max_slippage=0.5),
    "USDC": SlippageCurve(asset_symbol="USDC", a=2e-5, b=0.45, max_slippage=0.3),
    "stETH": SlippageCurve(asset_symbol="stETH", a=3e-4, b=0.55, max_slippage=0.4),
}


def slippage_for(symbol: str) -> SlippageCurve:
    return SLIPPAGE_CURVES.get(symbol, SlippageCurve(asset_symbol=symbol, a=3e-4, b=0.55))


def section(title: str) -> None:
    print("=" * 90)
    print(title)
    print("=" * 90)


def main() -> None:
    fixtures_root = ROOT / "data" / "fixtures"

    # =========================================================================
    section("Phase 5 — v0.3 backtest validation")
    # =========================================================================

    verdicts = []
    for eid in list_fixtures(fixtures_root):
        fixture = load_event(fixtures_root / eid)
        collateral = fixture.meta.affected_collaterals[0]
        curve = slippage_for(collateral)
        verdict = run_backtest(fixture, curve, n_mc_paths=200)
        verdicts.append(verdict)
        print(format_verdict(verdict))
        print()

    print(f"{'event_id':<28} {'expected':>10} {'flagged':>10} {'severity':>10} {'verdict':>10}")
    print("-" * 90)
    for v in verdicts:
        print(
            f"{v.event_id:<28} {str(v.expected_red_flag):>10} {str(v.framework_flagged):>10} "
            f"{v.severity_flag:>10} {v.pass_fail:>10}"
        )
    n_pass = sum(1 for v in verdicts if v.pass_fail == "PASS")
    print(f"\nPass rate: {n_pass}/{len(verdicts)}")
    print()

    # =========================================================================
    section("Slippage curve fit on synthetic Uniswap V3 swaps (demo)")
    # =========================================================================

    pool_specs = [
        ("wstETH", 200_000_000.0, 5),
        ("WBTC", 300_000_000.0, 5),
        ("sUSDe", 80_000_000.0, 5),
        ("weETH", 60_000_000.0, 30),
    ]
    print(f"{'asset':<10} {'pool TVL':>15} {'fee':>5} {'n_obs':>7} {'a_fit':>12} {'b_fit':>10} {'b SE':>10} {'R²':>8}")
    print("-" * 90)
    for asset, tvl, fee in pool_specs:
        df = synthesize_uniswap_swaps(asset, tvl, fee, n_swaps=500)
        result = fit_with_diagnostics(df, asset_symbol=asset)
        print(
            f"{asset:<10} ${tvl/1e6:>11,.0f}M {fee:>5} {result.n_observations:>7} "
            f"{result.curve.a:>12.4e} {result.curve.b:>10.4f} {result.b_se:>10.4f} "
            f"{result.r_squared:>8.3f}"
        )
    print()

    # =========================================================================
    section("Forward-looking risk on representative current markets")
    # =========================================================================

    print("Roster (mid-2026 representative markets):")
    for p in current_markets():
        print(
            f"  {p.market_label:<15} TVL=${p.total_supply_usd/1e6:>6,.0f}M  "
            f"U={p.utilization:>5.1%}  LLTV={p.lltv:>5.2%}  drawdown_p99={p.drawdown_p99:>5.1%}"
        )
    print()

    results = assess_all_markets(n_mc_paths=200)

    print(
        f"{'market':<15} {'sev':>6} {'LCR':>10} {'alpha':>8} {'TTI(h)':>8} "
        f"{'P[bd>0]':>10} {'p95 bd':>14} {'p99 bd':>14}"
    )
    print("-" * 100)
    for r in results:
        tti_str = f"{r.time_to_illiquid_hours:.2f}" if r.time_to_illiquid_hours != float("inf") else "  inf"
        print(
            f"{r.market_label:<15} {r.severity_flag:>6} {r.lcr_v03:>10.3f} {r.alpha_calibrated:>8.2%} "
            f"{tti_str:>8} {r.p_bad_debt_gt_0:>10.2%} ${r.p95_bad_debt_usd:>12,.0f} ${r.p99_bad_debt_usd:>12,.0f}"
        )
    print()

    n_red = sum(1 for r in results if r.severity_flag == "red")
    n_yellow = sum(1 for r in results if r.severity_flag == "yellow")
    n_green = sum(1 for r in results if r.severity_flag == "green")
    print(f"Severity distribution: red={n_red}  yellow={n_yellow}  green={n_green}")
    print()

    section("Phase 5 complete")
    print("Next: writeup as docs/REPORT.md and Mirror.xyz publication.")


if __name__ == "__main__":
    main()
