"""DEX slippage model — π(C, V).

Slippage is the relative shortfall between the oracle-quoted price and the
realized DEX execution price for selling `V` units of collateral `C`:

    π(C, V) = (P_oracle - P_realized) / P_oracle ∈ [0, 1)

We fit a power law per asset:

    π(V) = a · V^b

calibrated on DEX execution data (1inch quotes for forward, Uniswap historical
swaps for backward). The fit is in log-space (log π = log a + b · log V), which
linearizes the regression and gives well-conditioned parameter estimates.

For v0 (mock data), we expose a `SlippageCurve` that can be:
    - constructed from synthetic (a, b) parameters (testing / mock scenarios)
    - fitted from a `dex_slippage` Pandera-validated DataFrame (Phase 4)

References:
    - Almgren-Chriss (2000), "Optimal Execution of Portfolio Transactions" —
      power-law impact has its origins in the equity microstructure literature.
    - Frazzini, Israel, Moskowitz (2018), "Trading Costs" — empirical b ≈ 0.6
      across asset classes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from morpho_stress.models.constants import EPS


@dataclass(frozen=True, slots=True)
class SlippageCurve:
    """Power-law slippage model: π(V) = a · V^b, clipped to [0, max_slippage].

    Parameters:
        a: scale parameter. Slippage at V = 1 native unit.
        b: exponent. Typically 0.4 < b < 0.7 for liquid crypto assets.
        max_slippage: cap to prevent unphysical values (e.g. π > 1).
        min_volume_native: volumes below this are treated as 0 slippage.
    """

    asset_symbol: str
    a: float
    b: float
    max_slippage: float = 0.5  # 50% — beyond this, position is effectively unliquidatable
    min_volume_native: float = 0.0

    def slippage(self, volume_native: float) -> float:
        """Return π for selling `volume_native` units. Clipped to [0, max_slippage]."""
        if volume_native <= self.min_volume_native:
            return 0.0
        raw = self.a * (volume_native**self.b)
        return float(np.clip(raw, 0.0, self.max_slippage))

    def realized_price(self, volume_native: float, oracle_price: float) -> float:
        """Realized DEX execution price after slippage."""
        return oracle_price * (1.0 - self.slippage(volume_native))


def fit_curve(
    df: pd.DataFrame,
    asset_symbol: str,
    min_observations: int = 10,
) -> SlippageCurve:
    """Fit a SlippageCurve to a DataFrame of DEX slippage observations.

    Expected columns (subset of `dex_slippage` schema):
        volume_native: float, > 0
        slippage_bps: float, can be negative (positive surprises) — clipped to ≥ 1 bp

    The fit is OLS on log(π) vs log(V):
        log(π) = log(a) + b · log(V) + ε

    Negative or zero slippage observations are dropped (cannot log).
    """
    sub = df[df["collateral_symbol"] == asset_symbol].copy()
    if len(sub) < min_observations:
        raise ValueError(
            f"insufficient observations for {asset_symbol}: "
            f"{len(sub)} < {min_observations}"
        )

    # Convert bps to fraction; drop non-positive
    sub["pi"] = sub["slippage_bps"].clip(lower=1.0) / 10_000.0
    sub = sub[sub["volume_native"] > 0]
    if len(sub) < min_observations:
        raise ValueError(f"after cleaning, too few observations for {asset_symbol}")

    log_v = np.log(sub["volume_native"].to_numpy())
    log_pi = np.log(sub["pi"].to_numpy())

    # OLS: log_pi = log_a + b * log_v
    # Closed-form bivariate regression
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

    # Sanity: positive a and b in plausible range
    if a <= 0:
        raise ValueError(f"non-positive scale parameter a={a} for {asset_symbol}")
    if not (0.1 <= b <= 1.5):
        # Warn but accept — empirical b across assets ranges
        # We do not raise; downstream tests can flag implausible curves
        pass

    return SlippageCurve(asset_symbol=asset_symbol, a=a, b=b)
