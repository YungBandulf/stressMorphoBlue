"""Tests for the slippage curve model."""

from __future__ import annotations

import math

import numpy as np
import pytest

from morpho_stress.models.slippage import SlippageCurve, fit_curve
from morpho_stress.utils.mock import make_dex_slippage_observations


def test_curve_zero_volume_zero_slippage() -> None:
    curve = SlippageCurve(asset_symbol="X", a=1e-4, b=0.5)
    assert curve.slippage(0.0) == 0.0


def test_curve_monotonic_in_volume() -> None:
    curve = SlippageCurve(asset_symbol="X", a=1e-4, b=0.6)
    volumes = [1.0, 10.0, 100.0, 1000.0, 10_000.0]
    slippages = [curve.slippage(v) for v in volumes]
    for prev, nxt in zip(slippages, slippages[1:]):
        assert nxt >= prev


def test_curve_capped_at_max() -> None:
    curve = SlippageCurve(asset_symbol="X", a=10.0, b=1.0, max_slippage=0.5)
    assert curve.slippage(1e9) == 0.5


def test_realized_price_is_oracle_minus_slippage() -> None:
    curve = SlippageCurve(asset_symbol="X", a=1e-3, b=0.5)
    p_oracle = 2_000.0
    v = 100.0
    pi = curve.slippage(v)
    realized = curve.realized_price(v, p_oracle)
    assert math.isclose(realized, p_oracle * (1.0 - pi), rel_tol=1e-12)


def test_fit_curve_recovers_known_parameters() -> None:
    """If we generate from (a, b) and fit, we recover them within reasonable tolerance."""
    a_true = 1e-4
    b_true = 0.55
    df = make_dex_slippage_observations(
        asset_symbol="wstETH",
        n_observations=200,
        a_true=a_true,
        b_true=b_true,
        noise_bps=2.0,
        seed=42,
    )
    fitted = fit_curve(df, asset_symbol="wstETH")
    assert math.isclose(fitted.b, b_true, rel_tol=0.1)
    assert math.isclose(fitted.a, a_true, rel_tol=0.5)  # a is more sensitive to noise


def test_fit_curve_raises_on_insufficient_observations() -> None:
    df = make_dex_slippage_observations(asset_symbol="X", n_observations=5)
    with pytest.raises(ValueError, match="insufficient observations"):
        fit_curve(df, asset_symbol="X", min_observations=10)


def test_fit_curve_raises_on_unknown_asset() -> None:
    df = make_dex_slippage_observations(asset_symbol="X", n_observations=20)
    with pytest.raises(ValueError, match="insufficient"):
        fit_curve(df, asset_symbol="Y")
