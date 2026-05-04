"""Phase 3 demo — end-to-end stress test on synthetic data.

Run as a script:
    PYTHONPATH=src python notebooks/phase3_demo.py

Or convert to a Jupyter notebook with `jupytext --to ipynb phase3_demo.py`.

This script demonstrates the full Phase 3 pipeline on mock data:

1. Build a synthetic Morpho Blue market state
2. Calibrate a slippage curve
3. Run scenario S1 (withdrawal run) at three severities
4. Liquidate eligible positions under price stress
5. Print headline metrics
"""

# %%
from __future__ import annotations

import sys
from pathlib import Path

# Ensure local src is importable when run as a script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from morpho_stress.models.slippage import fit_curve  # noqa: E402
from morpho_stress.scenarios import (  # noqa: E402
    S1Config,
    liquidate_all_eligible,
    stress_s1,
    time_to_illiquid,
)
from morpho_stress.utils.mock import (  # noqa: E402
    make_dex_slippage_observations,
    make_market_state,
)


# %%
# ----- 1. Build a synthetic market -----
state = make_market_state(
    initial_supply=100_000_000.0,  # 100M USDC
    utilization=0.85,  # tight liquidity (15% headroom)
    oracle_price=2_000.0,  # WETH at 2000 USDC
    n_positions=200,
    avg_ltv=0.70,
    ltv_std=0.08,
    seed=42,
)

print("=" * 70)
print("Initial market state")
print("=" * 70)
print(f"  S (supply):       ${state.total_supply_assets:>15,.0f}")
print(f"  B (borrow):       ${state.total_borrow_assets:>15,.0f}")
print(f"  L (liquidity):    ${state.liquidity:>15,.0f}")
print(f"  U (utilization):  {state.utilization:>15.2%}")
print(f"  C (collateral):   {state.total_collateral:>15,.2f} WETH")
print(f"  P (oracle):       ${state.oracle_price:>15,.2f}")
print(f"  LLTV:             {state.params.lltv:>15.2%}")
print(f"  N positions:      {len(state.positions):>15}")


# %%
# ----- 2. Fit a slippage curve -----
slippage_obs = make_dex_slippage_observations(
    asset_symbol="WETH",
    n_observations=200,
    a_true=2e-4,
    b_true=0.55,
    noise_bps=3.0,
    seed=42,
)
curve = fit_curve(slippage_obs, asset_symbol="WETH")
print()
print("=" * 70)
print("Slippage curve fit")
print("=" * 70)
print(f"  a (recovered):    {curve.a:.4e}    (true: 2.00e-4)")
print(f"  b (recovered):    {curve.b:.4f}      (true: 0.5500)")
print()
print(f"  π(100 WETH):      {curve.slippage(100.0):.2%}")
print(f"  π(1000 WETH):     {curve.slippage(1000.0):.2%}")
print(f"  π(10000 WETH):    {curve.slippage(10000.0):.2%}")


# %%
# ----- 3. Scenario S1: withdrawal run at three severities -----
print()
print("=" * 70)
print("Scenario S1 — Withdrawal Run")
print("=" * 70)
print(f"{'alpha':>8} {'duration':>10} {'horizon':>10} {'queued (USD)':>20} {'TTI (blocks)':>15}")
print("-" * 70)

for alpha in [0.05, 0.15, 0.30]:
    cfg = S1Config(
        alpha=alpha,
        duration_blocks=7200,  # 24h
        horizon_blocks=7200,
        arrival="linear",
    )
    traj = stress_s1(state, cfg)
    queued = traj.final_state.queued_withdrawals
    tti = time_to_illiquid(traj)
    tti_str = str(tti) if tti is not None else "n/a"
    print(f"{alpha:>8.2%} {cfg.duration_blocks:>10} {cfg.horizon_blocks:>10} ${queued:>18,.0f}  {tti_str:>14}")


# %%
# ----- 4. Liquidations under price drop -----
print()
print("=" * 70)
print("Liquidations under price drops (oracle = market, exogenous regime)")
print("=" * 70)
print(f"{'price drop':>12} {'n liquidated':>15} {'bad debt (USD)':>20} {'avg slippage':>15}")
print("-" * 70)

for drop_pct in [0.05, 0.10, 0.15, 0.20, 0.30]:
    stressed = state.replace(oracle_price=state.oracle_price * (1.0 - drop_pct))
    outcomes, after = liquidate_all_eligible(
        stressed, market_price=stressed.oracle_price, slippage_curve=curve
    )
    n_liq = len(outcomes)
    bad_debt = sum(o.bad_debt_assets for o in outcomes)
    if outcomes:
        avg_pi = np.mean(
            [
                1.0 - (o.realized_loan_value / max(o.repaid_assets, 1e-9))
                if o.repaid_assets > 0 else 0
                for o in outcomes
            ]
        )
    else:
        avg_pi = 0.0
    print(f"{drop_pct:>12.2%} {n_liq:>15} ${bad_debt:>18,.0f}  {avg_pi:>14.2%}")


# %%
# ----- 5. Headline summary -----
print()
print("=" * 70)
print("Demo completed — Phase 3 pipeline functional on mock data")
print("=" * 70)
print()
print("Next: Phase 4 = backtest framework against historical events")
print("      (KelpDAO April 2026, USDC depeg March 2023, stETH May 2022)")
