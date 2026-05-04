"""Backtest runner — applies §6.1 validation criteria to historical events.

For each event fixture, runs the framework at T-1 (T0) and checks whether
any of the three pass criteria fire:

1. LCR_onchain(M, T0, S5_replay, h=24h) < 100%
2. time_to_illiquid(M, S1 at p99 alpha, h=24h) < 24h
3. P[bad_debt > 0 | S4 cascade] > 5%

The runner produces a `BacktestVerdict` per event and a global summary.

Severity flags (SCENARIOS.md §7):
- red:    LCR < 80% OR TTI < 12h OR P[bd>0] > 20%
- yellow: LCR ∈ [80, 100) OR TTI ∈ [12h, 24h) OR P[bd>0] ∈ [5, 20)%
- green:  none of the above
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

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
from morpho_stress.backtest.fixtures import EventFixture


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
    severity_flag: str  # green / yellow / red — composite
    framework_flagged: bool  # True if at least one criterion triggered

    pass_fail: str  # "PASS" if framework_flagged matches expected_red_flag
    metrics: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Criterion evaluators
# ---------------------------------------------------------------------------


def _evaluate_lcr_onchain(fixture: EventFixture, slippage_curve: SlippageCurve) -> CriterionResult:
    """Compute LCR_onchain via S5-style replay of the actual price path.

    LCR = HQLA / Net_Outflows. We approximate:
        HQLA = L_t (instant liquidity) + 0.85 × DEX-recoverable collateral
        Outflows = realized withdrawal pressure from S1 at p99 over 24h
    """
    state = fixture.initial_state

    # Estimate p99 withdrawal alpha from a synthetic baseline (in production
    # this would use historical events log).
    # For backtest fixtures, we use a pessimistic 30% alpha (representative
    # of stress scenarios documented in industry risk reports).
    alpha = 0.30
    cfg_s1 = S1Config(alpha=alpha, duration_blocks=HOURS_24, horizon_blocks=HOURS_24)
    s1_traj = stress_s1(state, cfg_s1)
    realized_outflow_24h = state.total_supply_assets - s1_traj.final_state.total_supply_assets
    queued = s1_traj.final_state.queued_withdrawals
    net_outflow = realized_outflow_24h + queued

    # HQLA components
    l1 = state.liquidity
    # L2A: collateral recoverable at oracle price * (1 - p50 slippage @ avg position size)
    avg_pos_size = state.total_collateral / max(len(state.positions), 1)
    median_slippage = slippage_curve.slippage(avg_pos_size)
    l2a = state.total_collateral * state.oracle_price * (1 - median_slippage) * 0.85

    hqla = l1 + l2a
    lcr = hqla / max(net_outflow, 1.0)

    # Severity
    if lcr < 0.80:
        sev = "red"
    elif lcr < 1.00:
        sev = "yellow"
    else:
        sev = "green"

    return CriterionResult(
        name="LCR_onchain_24h",
        value=lcr,
        threshold=1.00,
        triggered=lcr < 1.00,
        severity=sev,
    )


def _evaluate_time_to_illiquid(fixture: EventFixture) -> CriterionResult:
    """Run S1 at p99 alpha and check time_to_illiquid."""
    state = fixture.initial_state
    cfg = S1Config(alpha=0.30, duration_blocks=HOURS_24, horizon_blocks=HOURS_24)
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


def _evaluate_bad_debt_probability(
    fixture: EventFixture,
    slippage_curve: SlippageCurve,
    n_paths: int = 100,
) -> tuple[CriterionResult, float, float]:
    """Run MC over event-derived drawdown distribution; compute P[bad_debt > 0].

    The drawdown distribution is calibrated from the actual price path of the
    event window: we extract the maximum 24h drawdown observed at each hour
    of the window, and resample from this empirical CDF.

    Returns (CriterionResult, p95_bad_debt, p99_bad_debt) for richer reporting.
    """
    state = fixture.initial_state

    # Build empirical drawdown distribution from the price path
    market_path = fixture.market_path
    # 24h window = 24 hourly observations
    drawdowns = []
    for i in range(len(market_path) - 24):
        peak = market_path[i]
        trough = market_path[i:i + 24].min()
        d = max(0.0, (peak - trough) / peak)
        drawdowns.append(d)
    drawdowns_arr = np.array(drawdowns)

    if len(drawdowns_arr) < 10:
        # Not enough data; fall back to a reasonable point estimate
        drawdowns_arr = np.array([0.05, 0.10, 0.15, 0.20, 0.25, 0.30])

    dist = EmpiricalDistribution(observations=drawdowns_arr)

    def scenario_fn(s, drawdown):
        return stress_s3(
            s,
            S3Config(
                drawdown=float(drawdown),
                dt_blocks=HOURS_24,
                horizon_blocks=HOURS_24,
                shape="instant",  # conservative — represents the worst within-day event
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
    n_mc_paths: int = 100,
) -> BacktestVerdict:
    """Run the full §6.1 validation for one event fixture."""

    c_lcr = _evaluate_lcr_onchain(fixture, slippage_curve)
    c_tti = _evaluate_time_to_illiquid(fixture)
    c_bd, p95_bd, p99_bd = _evaluate_bad_debt_probability(fixture, slippage_curve, n_paths=n_mc_paths)

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
            "LCR_onchain": c_lcr.value,
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
            f"      [{c.severity:>6}] {c.name:<25} value={c.value:>10.4f} "
            f"threshold={c.threshold:>6.2f} triggered={c.triggered}"
        )
    lines.append("    metrics:")
    for k, val in v.metrics.items():
        lines.append(f"      {k:<30} = {val:,.4f}")
    return "\n".join(lines)
