"""Tests for oracle models."""

from __future__ import annotations

import math

import pytest

from morpho_stress.models.oracle import ExogenousOracle, TwapOracle, make_oracle


def test_exogenous_oracle_mirrors_input() -> None:
    o = ExogenousOracle(initial_price=100.0)
    assert o.read() == 100.0
    o.update(110.0, block=1)
    assert o.read() == 110.0
    o.update(95.0, block=2)
    assert o.read() == 95.0


def test_exogenous_oracle_rejects_zero_or_negative() -> None:
    o = ExogenousOracle(initial_price=100.0)
    o.update(0.0, block=1)
    assert o.read() == 100.0  # unchanged
    o.update(-50.0, block=2)
    assert o.read() == 100.0


def test_twap_oracle_window_smoothing() -> None:
    o = TwapOracle(initial_price=100.0, lambda_blocks=4)
    # Fill window with prices [100, 110, 120, 130]
    for p in [110.0, 120.0, 130.0]:
        o.update(p, block=1)
    # After 4 observations: mean of [100, 110, 120, 130] = 115
    assert math.isclose(o.read(), 115.0, rel_tol=1e-9)


def test_twap_oracle_evicts_old() -> None:
    o = TwapOracle(initial_price=100.0, lambda_blocks=2)
    o.update(200.0, block=1)
    # Window = [100, 200], mean = 150
    assert math.isclose(o.read(), 150.0, rel_tol=1e-9)
    o.update(300.0, block=2)
    # Window = [200, 300], mean = 250
    assert math.isclose(o.read(), 250.0, rel_tol=1e-9)


def test_twap_oracle_invalid_initial() -> None:
    with pytest.raises(ValueError):
        TwapOracle(initial_price=0.0, lambda_blocks=10)
    with pytest.raises(ValueError):
        TwapOracle(initial_price=-1.0, lambda_blocks=10)


def test_twap_oracle_invalid_lambda() -> None:
    with pytest.raises(ValueError):
        TwapOracle(initial_price=100.0, lambda_blocks=0)


def test_make_oracle_dispatches_correctly() -> None:
    o_chain = make_oracle("chainlink", initial_price=100.0)
    assert isinstance(o_chain, ExogenousOracle)

    o_twap = make_oracle("uniswap_twap", initial_price=100.0, lambda_blocks=30)
    assert isinstance(o_twap, TwapOracle)

    with pytest.raises(ValueError):
        make_oracle("nonexistent", initial_price=100.0)
