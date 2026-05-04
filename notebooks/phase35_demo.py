"""Phase 3.5 demo — Adaptive IRM + Geometric TWAP + S3 + Monte Carlo.

Runs the full Phase 3.5 stack on synthetic data:

1. Build a market with adaptive IRM
2. Run S3 oracle-deviation scenario across multiple drawdown levels (point mode)
3. Run Monte Carlo over an empirical drawdown distribution
4. Report distributional metrics

Usage:
    PYTHONPATH=src python notebooks/phase35_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from morpho_stress.models.slippage import SlippageCurve  # noqa: E402
from morpho_stress.scenarios import (  # noqa: E402
    EmpiricalDistribution,
    S3Config,
    cascade_depth,
    n_liquidated,
    run_monte_carlo,
    slippage_shortfall,
    stress_s3,
    total_bad_debt,
)
from morpho_stress.utils.mock import make_market_state  # noqa: E402


# ----- 1. Build a synthetic market with adaptive IRM -----
state = make_market_state(
    initial_supply=200_000_000.0,  # 200M USDC
    utilization=0.85,
    oracle_price=2_000.0,
    n_positions=300,
    avg_ltv=0.72,
    ltv_std=0.07,
    seed=42,
)

curve = SlippageCurve(asset_symbol="WETH", a=3e-4, b=0.58, max_slippage=0.5)


print("=" * 80)
print("Phase 3.5 demo — Morpho Blue liquidity stress")
print("=" * 80)
print()
print("Initial state:")
print(f"  S = ${state.total_supply_assets:,.0f}")
print(f"  B = ${state.total_borrow_assets:,.0f}    U = {state.utilization:.1%}")
print(f"  P_oracle = ${state.oracle_price:,.2f}")
print(f"  N positions = {len(state.positions)}    LLTV = {state.params.lltv:.0%}")
print(f"  IRM rate_at_target = {state.rate_at_target:.2%} (full adaptive)")
print()


# ----- 2. Point-mode S3 across drawdown levels -----
print("=" * 80)
print("S3 — Oracle deviation, point mode (6h drawdown, 24h horizon)")
print("=" * 90)
print(f"{'drawdown':>10} {'n_liq':>7} {'cascade':>9} {'bad_debt':>14} {'slip_short':>14}")
print("-" * 80)

dt_blocks = 1800       # 6h drawdown
horizon = 7200         # 24h horizon
print(f"{'drawdown':>10} {'shape':>10} {'n_liq':>7} {'cascade':>9} {'bad_debt':>14} {'slip_short':>14}")
print("-" * 90)
for shape in ["linear", "instant"]:
    for d in [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]:
        cfg = S3Config(drawdown=d, dt_blocks=dt_blocks, horizon_blocks=horizon, shape=shape)
        traj = stress_s3(state, cfg, curve)
        print(
            f"{d:>10.0%} {shape:>10} {n_liquidated(traj):>7} {cascade_depth(traj):>9} "
            f"${total_bad_debt(traj):>12,.0f} ${slippage_shortfall(traj):>12,.0f}"
        )


# ----- 3. Monte Carlo over empirical drawdown distribution -----
print()
print("=" * 80)
print("S3 — Monte Carlo over empirical drawdown distribution (instant shock, n=200)")
print("=" * 80)

# Synthesize an empirical distribution of 24h drawdowns for WETH.
# Heavy-tailed: most days small, occasional big shock. Beta-like with rare spikes.
rng = np.random.default_rng(42)
small_drawdowns = rng.beta(2, 30, 350) * 0.10        # bulk: 0–6%
medium_drawdowns = rng.beta(2, 5, 100) * 0.20        # tail: 0–20%
large_drawdowns = np.array([0.18, 0.22, 0.25, 0.28, 0.32, 0.35, 0.40])  # historical extremes
all_drawdowns = np.concatenate([small_drawdowns, medium_drawdowns, large_drawdowns])

dist = EmpiricalDistribution(observations=all_drawdowns)
print(
    f"  empirical p50 = {dist.quantile(0.5):.2%}    p95 = {dist.quantile(0.95):.2%}    "
    f"p99 = {dist.quantile(0.99):.2%}"
)
print()


def scenario_fn(s, drawdown):
    return stress_s3(
        s,
        S3Config(
            drawdown=drawdown, dt_blocks=dt_blocks, horizon_blocks=horizon, shape="instant"
        ),
        curve,
    )


metrics = {
    "n_liquidated": lambda t: float(n_liquidated(t)),
    "bad_debt_usd": total_bad_debt,
    "slippage_shortfall_usd": slippage_shortfall,
    "cascade_depth": lambda t: float(cascade_depth(t)),
}

results = run_monte_carlo(
    initial_state=state,
    distribution=dist,
    scenario_fn=scenario_fn,
    metric_fns=metrics,
    n_paths=200,
    seed=42,
)

print(f"{'metric':>26} {'mean':>14} {'p5':>12} {'p50':>12} {'p95':>14} {'p99':>14}")
print("-" * 100)
for name, res in results.items():
    print(
        f"{name:>26} {res.mean:>14,.2f} {res.p5:>12,.2f} {res.p50:>12,.2f} "
        f"{res.p95:>14,.2f} {res.p99:>14,.2f}"
    )


# ----- 4. Headline -----
bd = results["bad_debt_usd"]
print()
print("=" * 80)
print("Headline metrics")
print("=" * 80)
print(f"  Expected 7-day bad debt: ${bd.mean:,.0f}")
print(f"  95th percentile bad debt: ${bd.p95:,.0f}")
print(f"  99th percentile bad debt: ${bd.p99:,.0f}")
print(f"  Pr(bad_debt > 0) = {(bd.samples > 0).mean():.1%}")
print(f"  Pr(bad_debt > 1M) = {(bd.samples > 1_000_000).mean():.1%}")
print(f"  Pr(bad_debt > 10M) = {(bd.samples > 10_000_000).mean():.1%}")
print()
print("Phase 3.5 complete: full IRM + TWAP + S3 + MC operational on mock data.")
print("Next: Phase 4 = backtest against real historical events.")
