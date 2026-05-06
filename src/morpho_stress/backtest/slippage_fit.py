"""Slippage curve fitting from Uniswap V3 historical swaps.

Production fit pipeline (Phase 5+):

1. Pull historical swaps from the Uniswap V3 subgraph for the relevant
   collateral/loan pair (e.g., wstETH/USDC pool 0x...).
2. For each swap, compute realized slippage relative to the contemporaneous
   Chainlink oracle price.
3. Fit the SlippageCurve via OLS in log-space (already implemented in
   `models/slippage.fit_curve`).

This module focuses on the **data preparation** layer:

- Producing fixture-format swap CSVs from the Uniswap V3 schema
- Computing per-swap slippage given a contemporaneous oracle price series
- A reproducible fitter that takes a fixture CSV and produces a
  fitted `SlippageCurve` with confidence intervals

For the v0 demonstration, we ship synthetic-but-realistic swap data
calibrated to public Uniswap V3 pool stats. A "real fitter" mode is exposed
via `fit_from_subgraph_export()` for users with access to subgraph data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from morpho_stress.models.constants import EPS
from morpho_stress.models.slippage import SlippageCurve


@dataclass(frozen=True, slots=True)
class FitResult:
    """Outcome of a slippage curve fit with diagnostics."""

    curve: SlippageCurve
    n_observations: int
    r_squared: float
    log_a_se: float  # standard error on log(a)
    b_se: float  # standard error on b
    residual_std: float  # residual std in log space

    def confidence_interval_b(self, level: float = 0.95) -> tuple[float, float]:
        """Approximate Wald CI on b at the given confidence level (Gaussian)."""
        from scipy.stats import norm
        z = norm.ppf((1 + level) / 2)
        return (self.curve.b - z * self.b_se, self.curve.b + z * self.b_se)


def fit_with_diagnostics(
    df: pd.DataFrame,
    asset_symbol: str,
    min_observations: int = 20,
) -> FitResult:
    """Fit a SlippageCurve and return diagnostics.

    Expected columns on `df`:
        collateral_symbol, volume_native, slippage_bps

    Returns FitResult with the fitted curve plus R², parameter SEs, and
    residual std. Use these to decide whether the fit is trustworthy
    (e.g., R² < 0.4 ⇒ refit on cleaner data or change parametric form).
    """
    sub = df[df["collateral_symbol"] == asset_symbol].copy()
    sub = sub[(sub["volume_native"] > 0) & (sub["slippage_bps"] > 0)]
    if len(sub) < min_observations:
        raise ValueError(
            f"insufficient observations for {asset_symbol}: {len(sub)} < {min_observations}"
        )

    log_v = np.log(sub["volume_native"].to_numpy())
    log_pi = np.log((sub["slippage_bps"] / 10_000.0).to_numpy())

    n = len(log_v)
    mean_v = log_v.mean()
    mean_pi = log_pi.mean()
    var_v = ((log_v - mean_v) ** 2).sum()
    if var_v < EPS:
        raise ValueError(f"degenerate volume distribution for {asset_symbol}")

    cov_vp = ((log_v - mean_v) * (log_pi - mean_pi)).sum()
    b = cov_vp / var_v
    log_a = mean_pi - b * mean_v
    a = float(np.exp(log_a))

    # Residuals & R²
    fitted = log_a + b * log_v
    residuals = log_pi - fitted
    ss_res = float((residuals ** 2).sum())
    ss_tot = float(((log_pi - mean_pi) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > EPS else 0.0
    residual_std = float(np.sqrt(ss_res / max(n - 2, 1)))

    # OLS standard errors
    b_se = residual_std / np.sqrt(var_v)
    log_a_se = residual_std * np.sqrt(1.0 / n + (mean_v ** 2) / var_v)

    return FitResult(
        curve=SlippageCurve(asset_symbol=asset_symbol, a=a, b=b),
        n_observations=n,
        r_squared=r_squared,
        log_a_se=float(log_a_se),
        b_se=float(b_se),
        residual_std=residual_std,
    )


def fit_from_subgraph_export(
    csv_path: str | Path,
    asset_symbol: str,
    min_observations: int = 20,
) -> FitResult:
    """Convenience: load a subgraph CSV export and fit.

    The CSV must contain columns: collateral_symbol, volume_native, slippage_bps
    (matching the `dex_slippage` schema from `data/schemas.py`).
    """
    df = pd.read_csv(csv_path)
    return fit_with_diagnostics(df, asset_symbol=asset_symbol, min_observations=min_observations)


def synthesize_uniswap_swaps(
    asset_symbol: str,
    pool_size_usd: float,
    fee_tier_bps: int,
    n_swaps: int = 1000,
    base_b: float = 0.55,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthesize realistic Uniswap V3 swap fixture for a given pool.

    Calibrated to public pool statistics:
        - pool_size_usd: TVL in the pool (used to derive scale of `a`)
        - fee_tier_bps: 5 / 30 / 100 — affects baseline slippage
        - base_b: empirical Almgren-Chriss exponent (~0.55 for liquid crypto)

    The returned DataFrame matches the `dex_slippage` schema and can be fed
    directly to `fit_with_diagnostics`.

    Note: This is for demo purposes. In production, replace with real
    subgraph data via `fit_from_subgraph_export`.
    """
    rng = np.random.default_rng(seed)

    # Power-law a parameter scales inversely with pool depth.
    # For a $100M pool with 5bps fee, observed a ≈ 1e-4.
    # Scale: a = 1e-4 × (1e8 / pool_size_usd) × (fee_tier_bps / 5)
    a_true = 1e-4 * (1e8 / max(pool_size_usd, 1e6)) * (fee_tier_bps / 5)

    # Volumes log-uniform from $1k to $10M USD notional
    log_vol_usd = rng.uniform(np.log(1e3), np.log(1e7), n_swaps)
    volumes_usd = np.exp(log_vol_usd)

    # Convert to native units assuming reference price (we use 1 native = $1
    # for stables and $2000 for ETH-like; documented in caller)
    if asset_symbol.upper() in {"USDC", "USDT", "DAI", "USDE", "SUSDE"}:
        ref_price = 1.0
    elif asset_symbol.upper() in {"WBTC", "CBBTC"}:
        ref_price = 50_000.0
    else:
        ref_price = 2_000.0  # ETH-like
    volumes_native = volumes_usd / ref_price

    # Slippage in bps with multiplicative log-normal noise
    pi_true = a_true * volumes_native ** base_b
    log_noise = rng.normal(0.0, 0.20, n_swaps)
    pi_observed = np.clip(pi_true * np.exp(log_noise), 1e-6, 0.5)
    slippage_bps = pi_observed * 10_000.0

    # Realized = oracle × (1 - π)
    realized_prices = ref_price * (1.0 - pi_observed)

    return pd.DataFrame(
        {
            "collateral_symbol": asset_symbol,
            "quote_ts": pd.date_range(
                "2025-11-01", periods=n_swaps, freq="1h", tz="UTC"
            ),
            "direction": "sell_collateral_for_loan",
            "volume_usd": volumes_usd,
            "volume_native": volumes_native,
            "oracle_price": ref_price,
            "realized_price": realized_prices,
            "slippage_bps": slippage_bps,
            "source": f"synthesized:uniswap_v3_{fee_tier_bps}bps_pool",
        }
    )
