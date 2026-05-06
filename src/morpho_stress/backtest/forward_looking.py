"""Forward-looking stress analysis on current Morpho Blue markets.

This module applies the v0.3 framework to a roster of currently-deployed
Morpho Blue markets to produce risk rankings.

In a production deployment, the market roster would be loaded from the live
RPC + subgraph pipeline (Phase 2 fetchers). For the v0 demonstration, we
expose a `MarketProfile` dataclass and ship a fixture-style `current_markets()`
helper with parameters representative of mid-2026 Morpho Blue markets.

Output: ranked list of `MarketRiskAssessment` per market, suitable for
dashboard rendering and the public report.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

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
from morpho_stress.scenarios.state import MarketParams, MarketState, Position


HOURS_24 = int(24 * 3600 / BLOCK_TIME_SEC)


@dataclass(frozen=True, slots=True)
class MarketProfile:
    """A representative Morpho Blue market for forward-looking analysis."""

    market_label: str
    loan_symbol: str
    collateral_symbol: str
    total_supply_usd: float
    utilization: float
    n_positions: int
    avg_ltv: float
    lltv: float
    oracle_price: float
    rate_at_target: float
    oracle_kind: str = "chainlink"
    # Slippage curve parameters for the collateral (fitted from Uniswap V3 data
    # in production; these defaults are calibrated to liquid mid-2026 markets)
    slippage_a: float = 3e-4
    slippage_b: float = 0.55
    # Historical-event-equivalent drawdown distribution. Loaded from real
    # market observations in production; here we use plausible quantiles.
    drawdown_p50: float = 0.02
    drawdown_p99: float = 0.12


@dataclass(frozen=True, slots=True)
class MarketRiskAssessment:
    """Output of the forward-looking risk evaluation."""

    market_label: str
    severity_flag: str
    lcr_v03: float
    alpha_calibrated: float
    time_to_illiquid_hours: float
    p_bad_debt_gt_0: float
    p95_bad_debt_usd: float
    p99_bad_debt_usd: float
    expected_bad_debt_lcr: float


def current_markets() -> list[MarketProfile]:
    """Roster of representative Morpho Blue markets, mid-2026.

    In production, replace with output of `scripts/select_markets.py` and
    real on-chain state.
    """
    return [
        MarketProfile(
            market_label="wstETH/USDC",
            loan_symbol="USDC",
            collateral_symbol="wstETH",
            total_supply_usd=350_000_000.0,
            utilization=0.88,
            n_positions=420,
            avg_ltv=0.72,
            lltv=0.86,
            oracle_price=4_500.0,
            rate_at_target=0.045,
            slippage_a=2e-4,
            slippage_b=0.52,
            drawdown_p50=0.025,
            drawdown_p99=0.14,
        ),
        MarketProfile(
            market_label="WBTC/USDC",
            loan_symbol="USDC",
            collateral_symbol="WBTC",
            total_supply_usd=180_000_000.0,
            utilization=0.84,
            n_positions=210,
            avg_ltv=0.68,
            lltv=0.86,
            oracle_price=98_000.0,
            rate_at_target=0.038,
            slippage_a=1.5e-4,
            slippage_b=0.50,
            drawdown_p50=0.03,
            drawdown_p99=0.16,
        ),
        MarketProfile(
            market_label="cbBTC/USDC",
            loan_symbol="USDC",
            collateral_symbol="cbBTC",
            total_supply_usd=95_000_000.0,
            utilization=0.91,
            n_positions=160,
            avg_ltv=0.74,
            lltv=0.86,
            oracle_price=98_000.0,
            rate_at_target=0.052,
            slippage_a=4e-4,
            slippage_b=0.58,
            drawdown_p50=0.03,
            drawdown_p99=0.16,
        ),
        MarketProfile(
            market_label="sUSDe/USDC",
            loan_symbol="USDC",
            collateral_symbol="sUSDe",
            total_supply_usd=140_000_000.0,
            utilization=0.93,
            n_positions=85,
            avg_ltv=0.86,  # leveraged stable carry
            lltv=0.915,
            oracle_price=1.06,
            rate_at_target=0.085,
            slippage_a=8e-4,
            slippage_b=0.62,
            drawdown_p50=0.005,
            drawdown_p99=0.06,  # USDe historical max drawdown ~6%
        ),
        MarketProfile(
            market_label="weETH/USDC",
            loan_symbol="USDC",
            collateral_symbol="weETH",
            total_supply_usd=80_000_000.0,
            utilization=0.89,
            n_positions=140,
            avg_ltv=0.74,
            lltv=0.86,
            oracle_price=4_700.0,
            rate_at_target=0.058,
            slippage_a=6e-4,
            slippage_b=0.60,
            drawdown_p50=0.03,
            drawdown_p99=0.18,  # LRT collateral, post-KelpDAO repricing
        ),
    ]


def _profile_to_state(p: MarketProfile, seed: int = 42) -> MarketState:
    """Convert MarketProfile to a MarketState ready for stress simulation."""
    rng = np.random.default_rng(seed)
    total_supply = p.total_supply_usd  # denominate in loan asset (USDC = USD)
    total_borrow = total_supply * p.utilization

    weights = rng.dirichlet(np.ones(p.n_positions))
    pos_borrow = total_borrow * weights
    raw_ltvs = rng.normal(p.avg_ltv, 0.06, p.n_positions)
    cap = p.lltv - 1e-4
    ltvs = np.clip(raw_ltvs, 0.05, cap)
    pos_collateral = pos_borrow / (ltvs * p.oracle_price)

    positions = tuple(
        Position(
            borrower="0x" + f"{(seed * 1000003 + i) % (1 << 160):040x}",
            collateral=float(pos_collateral[i]),
            borrow_shares=float(pos_borrow[i]),  # 1:1 at construction
        )
        for i in range(p.n_positions)
    )

    params = MarketParams(
        market_id="0x" + f"{hash(p.market_label) & ((1 << 256) - 1):064x}",
        loan_decimals=6,
        collateral_decimals=18,
        lltv=p.lltv,
        fee=0.0,
        irm_initial_rate_at_target=p.rate_at_target,
        oracle_kind=p.oracle_kind,
    )

    return MarketState(
        params=params,
        block=22_000_000,
        block_ts=1_746_000_000,
        total_supply_assets=total_supply,
        total_supply_shares=total_supply,
        total_borrow_assets=total_borrow,
        total_borrow_shares=total_borrow,
        total_collateral=float(pos_collateral.sum()),
        oracle_price=p.oracle_price,
        rate_at_target=p.rate_at_target,
        positions=positions,
    )


def _drawdown_distribution(p: MarketProfile, n: int = 200) -> EmpiricalDistribution:
    """Build a Beta-distributed drawdown sample matching the profile's
    p50 and p99.

    For the v0, we use a simple Beta(2, k) with k chosen to match p99.
    A v1 extension would fit a heavy-tailed distribution (Pareto / GPD)
    on real history.
    """
    rng = np.random.default_rng(42)
    # Simple parameterization: scale Beta(2, 8) to hit p99 ≈ 0.14
    base = rng.beta(2, 8, n)
    # Rescale so empirical p99 matches profile.drawdown_p99
    scale = p.drawdown_p99 / float(np.quantile(base, 0.99))
    samples = np.clip(base * scale, 0.0, 1.0)
    return EmpiricalDistribution(observations=samples)


def assess_market(
    profile: MarketProfile, n_mc_paths: int = 200, seed: int = 42
) -> MarketRiskAssessment:
    """Run the full v0.3 risk evaluation on one market profile."""
    state = _profile_to_state(profile, seed=seed)
    curve = SlippageCurve(
        asset_symbol=profile.collateral_symbol,
        a=profile.slippage_a,
        b=profile.slippage_b,
    )

    # Build a synthetic price path representative of the drawdown profile,
    # used to derive the calibrated alpha.
    rng = np.random.default_rng(seed)
    n_hours = 240  # 10-day window
    path = np.full(n_hours, profile.oracle_price)
    # Inject a single p99 drawdown event in the middle of the window
    event_start = n_hours // 2
    drop = profile.drawdown_p99
    for i in range(24):
        path[event_start + i] *= 1.0 - drop * (i / 24)
    path += rng.normal(0, profile.oracle_price * 0.005, n_hours)

    alpha = calibrated_outflow_alpha(path)

    # 1. LCR v0.3 — using drawdown_p99 as the stress price
    worst_price = profile.oracle_price * (1.0 - profile.drawdown_p99)
    lcr, comp = lcr_onchain_v03(
        state=state, market_price=worst_price, slippage_curve=curve, outflow_alpha=alpha
    )

    # 2. TTI under calibrated alpha
    cfg_s1 = S1Config(alpha=alpha, duration_blocks=HOURS_24, horizon_blocks=HOURS_24)
    s1_traj = stress_s1(state, cfg_s1)
    tti = time_to_illiquid(s1_traj)
    tti_hours = tti * BLOCK_TIME_SEC / 3600 if tti is not None else float("inf")

    # 3. P[bad_debt > 0] via MC over drawdown distribution
    dist = _drawdown_distribution(profile)

    def scenario_fn(s, drawdown):
        return stress_s3(
            s,
            S3Config(
                drawdown=float(drawdown),
                dt_blocks=HOURS_24,
                horizon_blocks=HOURS_24,
                shape="instant",
            ),
            curve,
        )

    mc_results = run_monte_carlo(
        initial_state=state,
        distribution=dist,
        scenario_fn=scenario_fn,
        metric_fns={
            "bad_debt": total_bad_debt,
            "n_liq": lambda t: float(n_liquidated(t)),
        },
        n_paths=n_mc_paths,
        seed=seed,
    )
    bd = mc_results["bad_debt"]
    p_bd = float((bd.samples > 0).mean())

    # Composite severity (worst of the three)
    severities = []
    severities.append("red" if lcr < 0.80 else "yellow" if lcr < 1.00 else "green")
    severities.append("red" if tti_hours < 12 else "yellow" if tti_hours < 24 else "green")
    severities.append("red" if p_bd > 0.20 else "yellow" if p_bd > 0.05 else "green")
    if "red" in severities:
        composite = "red"
    elif "yellow" in severities:
        composite = "yellow"
    else:
        composite = "green"

    return MarketRiskAssessment(
        market_label=profile.market_label,
        severity_flag=composite,
        lcr_v03=lcr,
        alpha_calibrated=alpha,
        time_to_illiquid_hours=tti_hours,
        p_bad_debt_gt_0=p_bd,
        p95_bad_debt_usd=bd.p95,
        p99_bad_debt_usd=bd.p99,
        expected_bad_debt_lcr=comp["expected_bad_debt"],
    )


def assess_all_markets(
    profiles: list[MarketProfile] | None = None, n_mc_paths: int = 200
) -> list[MarketRiskAssessment]:
    """Run forward-looking analysis on a roster of markets, sorted by severity."""
    if profiles is None:
        profiles = current_markets()
    results = [assess_market(p, n_mc_paths=n_mc_paths) for p in profiles]
    # Sort: red > yellow > green; within band, by P[bad_debt > 0] desc
    sev_rank = {"red": 0, "yellow": 1, "green": 2}
    return sorted(results, key=lambda r: (sev_rank[r.severity_flag], -r.p_bad_debt_gt_0))
