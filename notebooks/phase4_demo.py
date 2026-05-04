"""Phase 4 demo — backtest the framework against 3 historical events.

Runs the §6.1 validation criteria on each event fixture and reports the
composite verdict.

Usage:
    PYTHONPATH=src python notebooks/phase4_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from morpho_stress.backtest import (  # noqa: E402
    format_verdict,
    list_fixtures,
    load_event,
    run_backtest,
)
from morpho_stress.models.slippage import SlippageCurve  # noqa: E402


# Per-asset slippage curves. Calibrated to be conservative (representative of
# stress conditions, not normal liquidity). In production these would be fit
# from Uniswap V3 trades around the event window.
SLIPPAGE_CURVES = {
    "rsETH": SlippageCurve(asset_symbol="rsETH", a=5e-4, b=0.60, max_slippage=0.5),
    "USDC": SlippageCurve(asset_symbol="USDC", a=2e-5, b=0.45, max_slippage=0.3),
    "stETH": SlippageCurve(asset_symbol="stETH", a=3e-4, b=0.55, max_slippage=0.4),
}


def slippage_for(symbol: str) -> SlippageCurve:
    if symbol in SLIPPAGE_CURVES:
        return SLIPPAGE_CURVES[symbol]
    # Fallback: moderate curve
    return SlippageCurve(asset_symbol=symbol, a=3e-4, b=0.55)


def main() -> None:
    fixtures_root = ROOT / "data" / "fixtures"
    event_ids = list_fixtures(fixtures_root)

    print("=" * 90)
    print("Phase 4 — Backtest validation against historical events")
    print("=" * 90)
    print(f"Events found: {event_ids}")
    print()

    verdicts = []
    for eid in event_ids:
        fixture = load_event(fixtures_root / eid)
        # Pick slippage curve based on collateral asset
        collateral = fixture.meta.affected_collaterals[0]
        curve = slippage_for(collateral)
        verdict = run_backtest(fixture, curve, n_mc_paths=200)
        verdicts.append(verdict)
        print(format_verdict(verdict))
        print()

    # Global summary
    print("=" * 90)
    print("Global summary")
    print("=" * 90)
    print(f"{'event_id':<28} {'expected':>10} {'flagged':>10} {'severity':>10} {'verdict':>10}")
    print("-" * 90)
    for v in verdicts:
        print(
            f"{v.event_id:<28} {str(v.expected_red_flag):>10} {str(v.framework_flagged):>10} "
            f"{v.severity_flag:>10} {v.pass_fail:>10}"
        )
    print()

    # Aggregate
    n_pass = sum(1 for v in verdicts if v.pass_fail == "PASS")
    n_total = len(verdicts)
    print(f"Pass rate: {n_pass}/{n_total}")
    kelpdao = next((v for v in verdicts if v.event_id == "kelpdao_2026_04"), None)
    if kelpdao:
        kelpdao_status = "PASS" if kelpdao.pass_fail == "PASS" else "FAIL (CRITICAL)"
        print(f"KelpDAO (primary anchor): {kelpdao_status}")

    # Honest caveats
    print()
    print("Caveats (per docs/BACKTEST.md §6):")
    print("  - USDC and stETH events are counterfactual (predate Morpho Blue).")
    print("  - Position distribution synthesized; no historical position-level data.")
    print("  - Slippage curves are calibrated to represent event-time conditions, not")
    print("    fitted from real Uniswap historical swaps in this demo.")
    print("  - 3 events is a small sample; results are indicative, not statistically")
    print("    significant.")


if __name__ == "__main__":
    main()
