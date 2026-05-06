"""Backtest runner v0.3 — applies §6.1 validation criteria with event-calibrated parameters.

v0.3 changes vs v0.2 (Phase 4):

1. **LCR_onchain v0.3**: replaces total_collateral × oracle × 0.85 (which
   over-counted pledged collateral) with per-position recovery valuation
   (`lcr_onchain_v03` in `liquidity_metrics.py`). HQLA L2A is now bounded
   above by per-position debt (you cannot recover more than you're owed).

2. **Event-calibrated outflow alpha**: replaces the fixed α=30% with a value
   derived from the event's own price drawdown distribution. This makes TTI
   actually discriminate between events.

3. **Cleaner severity bands** with documented thresholds aligned with
   industry practice (Gauntlet, ChaosLabs).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from morpho_stress.backtest.fixtures import EventFixture
from morpho_stress.backtest.liquidity_metrics import (
    calibrated_outflow_alpha,
    lcr_onchain_v03,
)
from morpho_stress.models.constants import BLOCK_TIME_SEC
from morpho_stress.models.slippage import SlippageCurve
from morpho_stress.scenarios import (
    EmpiricalDistribution,
    S1Config,
    S3Config,
    n_liquidated,
    run_monte_carlo,
    stress_s1,
    stress_s3,
    time_to_illiquid,
    total_bad_debt,
)


# Convert hours → blocks (Ethereum 12s/block)
HOURS_24 = int(24 * 3600 / BLOCK_TIME_SEC)
HOURS_12 = int(12 * 3600 / BLOCK_TIME_SEC)


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """Outcome of one of the 3 validation criteria."""

    name: str
    value: float
    threshold: float
    triggered: bool
    severity: str  # green / yellow / red


@dataclass(frozen=True, slots=True)
class BacktestVerdict:
    """Verdict for a single event."""

    event_id: str
    event_name: str
    counterfactual: bool
    expected_red_flag: bool

    criteria: tuple[CriterionResult, ...]
    severity_flag: str
    framework_flagged: bool

    pass_fail: str
    metrics: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Criterion 1: LCR_onchain v0.3
# ---------------------------------------------------------------------------


def _evaluate_lcr_onchain(
    fixture: EventFixture,
    slippage_curve: SlippageCurve,
    outflow_alpha: float,
) -> tuple[CriterionResult, dict[str, float]]:
    """LCR_onchain v0.3 evaluation at T0.

    Uses the *worst observed market price* from the event window as the
    stress price for HQLA recovery valuation. This is conservative: it asks
    "if liquidations had to happen at the worst price seen, what would the
    LCR look like?".
    """
    state = fixture.initial_state
    worst_price = float(fixture.market_path.min())

    lcr, components = lcr_onchain_v03(
        state=state,
        market_price=worst_price,
        slippage_curve=slippage_curve,
        outflow_alpha=outflow_alpha,
    )

    if lcr < 0.80:
        sev = "red"
    elif lcr < 1.00:
        sev = "yellow"
    else:
        sev = "green"

    return (
        CriterionResult(
            name="LCR_onchain_v03",
            value=lcr,
            threshold=1.00,
            triggered=lcr < 1.00,
            severity=sev,
        ),
        components,
    )


# ---------------------------------------------------------------------------
# Criterion 2: time_to_illiquid (event-calibrated alpha)
# ---------------------------------------------------------------------------


def _evaluate_time_to_illiquid(
    fixture: EventFixture, outflow_alpha: float
) -> CriterionResult:
    """Run S1 at event-calibrated alpha and check time_to_illiquid."""
    state = fixture.initial_state
    cfg = S1Config(
        alpha=outflow_alpha,
        duration_blocks=HOURS_24,
        horizon_blocks=HOURS_24,
    )
    traj = stress_s1(state, cfg)
    tti = time_to_illiquid(traj)
    tti_hours = tti * BLOCK_TIME_SEC / 3600 if tti is not None else float("inf")

    if tti_hours < 12:
        sev = "red"
    elif tti_hours < 24:
        sev = "yellow"
    else:
        sev = "green"

    return CriterionResult(
        name="time_to_illiquid_24h",
        value=tti_hours,
        threshold=24.0,
        triggered=tti_hours < 24.0,
        severity=sev,
    )


# ---------------------------------------------------------------------------
# Criterion 3: P[bad_debt > 0]
# ---------------------------------------------------------------------------


def _evaluate_bad_debt_probability(
    fixture: EventFixture,
    slippage_curve: SlippageCurve,
    n_paths: int = 200,
) -> tuple[CriterionResult, float, float]:
    """MC over event-derived drawdown distribution; compute P[bad_debt > 0]."""
    state = fixture.initial_state

    # Build empirical drawdown distribution from the price path
    market_path = fixture.market_path
    drawdowns = []
    for i in range(len(market_path) - 24):
        peak = market_path[i]
        if peak <= 0:
            continue
        trough = market_path[i:i + 24].min()
        drawdowns.append(max(0.0, (peak - trough) / peak))
    drawdowns_arr = np.array(drawdowns) if drawdowns else np.array([0.05, 0.10, 0.20, 0.30])

    dist = EmpiricalDistribution(observations=drawdowns_arr)

    def scenario_fn(s, drawdown):
        return stress_s3(
            s,
            S3Config(
                drawdown=float(drawdown),
                dt_blocks=HOURS_24,
                horizon_blocks=HOURS_24,
                shape="instant",
            ),
            slippage_curve,
        )

    metrics = {
        "bad_debt": total_bad_debt,
        "n_liq": lambda t: float(n_liquidated(t)),
    }
    results = run_monte_carlo(
        initial_state=state,
        distribution=dist,
        scenario_fn=scenario_fn,
        metric_fns=metrics,
        n_paths=n_paths,
        seed=42,
    )

    bd = results["bad_debt"]
    p_bad_debt = float((bd.samples > 0).mean())

    if p_bad_debt > 0.20:
        sev = "red"
    elif p_bad_debt > 0.05:
        sev = "yellow"
    else:
        sev = "green"

    return (
        CriterionResult(
            name="P_bad_debt_gt_0",
            value=p_bad_debt,
            threshold=0.05,
            triggered=p_bad_debt > 0.05,
            severity=sev,
        ),
        bd.p95,
        bd.p99,
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def _composite_severity(severities: list[str]) -> str:
    if "red" in severities:
        return "red"
    if "yellow" in severities:
        return "yellow"
    return "green"


def run_backtest(
    fixture: EventFixture,
    slippage_curve: SlippageCurve,
    n_mc_paths: int = 200,
) -> BacktestVerdict:
    """Run the full §6.1 validation v0.3 for one event fixture."""

    # Step 1: derive event-calibrated alpha from the price path
    alpha = calibrated_outflow_alpha(fixture.market_path)

    # Step 2: evaluate the 3 criteria
    c_lcr, lcr_components = _evaluate_lcr_onchain(fixture, slippage_curve, alpha)
    c_tti = _evaluate_time_to_illiquid(fixture, alpha)
    c_bd, p95_bd, p99_bd = _evaluate_bad_debt_probability(
        fixture, slippage_curve, n_paths=n_mc_paths
    )

    criteria = (c_lcr, c_tti, c_bd)
    severity = _composite_severity([c.severity for c in criteria])
    flagged = any(c.triggered for c in criteria)
    expected = fixture.meta.expected_red_flag
    pass_fail = "PASS" if flagged == expected else "FAIL"

    return BacktestVerdict(
        event_id=fixture.event_id,
        event_name=fixture.meta.event_name,
        counterfactual=fixture.meta.counterfactual,
        expected_red_flag=expected,
        criteria=criteria,
        severity_flag=severity,
        framework_flagged=flagged,
        pass_fail=pass_fail,
        metrics={
            "outflow_alpha_calibrated": alpha,
            "LCR_onchain_v03": c_lcr.value,
            "L1_instant": lcr_components["L1_instant"],
            "L2A_net_recoverable": lcr_components["L2A_net_recoverable"],
            "expected_bad_debt_LCR": lcr_components["expected_bad_debt"],
            "HQLA_total": lcr_components["HQLA_total"],
            "net_outflows": lcr_components["net_outflows"],
            "time_to_illiquid_hours": c_tti.value,
            "P_bad_debt_gt_0": c_bd.value,
            "p95_bad_debt": p95_bd,
            "p99_bad_debt": p99_bd,
        },
    )


def format_verdict(v: BacktestVerdict) -> str:
    """Render a verdict as a human-readable summary."""
    lines = [
        f"=== {v.event_id} — {v.event_name}",
        f"    counterfactual: {v.counterfactual}    expected_red_flag: {v.expected_red_flag}",
        f"    framework_flagged: {v.framework_flagged}    severity: {v.severity_flag}    {v.pass_fail}",
        "    criteria:",
    ]
    for c in v.criteria:
        lines.append(
            f"      [{c.severity:>6}] {c.name:<25} value={c.value:>12.4f} "
            f"threshold={c.threshold:>6.2f} triggered={c.triggered}"
        )
    lines.append("    metrics:")
    for k, val in v.metrics.items():
        lines.append(f"      {k:<30} = {val:>16,.4f}")
    return "\n".join(lines)
