"""Tests for oracle models — exogenous + Uniswap-V3 geometric TWAP."""

from __future__ import annotations

import math

import pytest

from morpho_stress.models.oracle import (
    ExogenousOracle,
    TwapOracle,
    make_oracle,
    price_to_tick,
    tick_to_price,
)

# ---------------------------------------------------------------------------
# Tick / price conversions
# ---------------------------------------------------------------------------


def test_tick_price_roundtrip() -> None:
    for p in [1.0, 100.0, 2_000.0, 1e-3, 1e6]:
        t = price_to_tick(p)
        recovered = tick_to_price(t)
        assert math.isclose(recovered, p, rel_tol=1e-12)


def test_price_to_tick_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        price_to_tick(0.0)
    with pytest.raises(ValueError):
        price_to_tick(-1.0)


def test_tick_at_one_is_zero() -> None:
    """log_{1.0001}(1) = 0."""
    assert math.isclose(price_to_tick(1.0), 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Exogenous oracle
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Uniswap-V3 geometric TWAP
# ---------------------------------------------------------------------------


def test_twap_constant_price_is_constant() -> None:
    """If all observations are at the same price, TWAP equals that price."""
    o = TwapOracle(initial_price=100.0, lambda_blocks=10)
    for b in range(1, 5):
        o.update(100.0, block=b)
    assert math.isclose(o.read(), 100.0, rel_tol=1e-9)


def test_twap_geometric_not_arithmetic() -> None:
    """For prices [100, 400], geomean = 200 (= sqrt(100*400)), arithmean = 250.

    With observations [100 at block 0, 400 at block 1], time weights are equal.
    The geomean must be 200, not 250.
    """
    o = TwapOracle(initial_price=100.0, lambda_blocks=2)
    o.update(400.0, block=1)
    twap = o.read()
    # Should be very close to geomean = 200, far from arithmean = 250
    assert math.isclose(twap, 200.0, rel_tol=0.05)
    # Definitely not arithmean
    assert abs(twap - 250.0) > 10.0


def test_twap_window_eviction() -> None:
    """Old observations must be evicted from the window."""
    o = TwapOracle(initial_price=100.0, lambda_blocks=2)
    o.update(200.0, block=1)
    # Window holds [100, 200], geomean ≈ 141.4
    twap1 = o.read()
    assert 130 < twap1 < 160
    o.update(400.0, block=2)
    # Window holds [200, 400], geomean ≈ 282.8
    twap2 = o.read()
    assert 260 < twap2 < 310


def test_twap_oracle_invalid_initial() -> None:
    with pytest.raises(ValueError):
        TwapOracle(initial_price=0.0, lambda_blocks=10)
    with pytest.raises(ValueError):
        TwapOracle(initial_price=-1.0, lambda_blocks=10)


def test_twap_oracle_invalid_lambda() -> None:
    with pytest.raises(ValueError):
        TwapOracle(initial_price=100.0, lambda_blocks=0)


def test_twap_lambda_one_returns_latest() -> None:
    """A 1-block window is essentially a passthrough."""
    o = TwapOracle(initial_price=100.0, lambda_blocks=1)
    o.update(200.0, block=1)
    assert math.isclose(o.read(), 200.0, rel_tol=1e-9)


def test_twap_smooths_spike() -> None:
    """A single-block spike should NOT propagate fully into TWAP."""
    o = TwapOracle(initial_price=100.0, lambda_blocks=10)
    # 9 normal blocks, 1 spike
    for b in range(1, 10):
        o.update(100.0, block=b)
    o.update(1_000.0, block=10)
    twap = o.read()
    # Spike weighted at 1/10 in log-space ⇒ price = 100^(0.9) × 1000^(0.1) ≈ 125.9
    expected = math.exp(0.9 * math.log(100.0) + 0.1 * math.log(1000.0))
    assert math.isclose(twap, expected, rel_tol=0.05)


def test_twap_geomean_is_log_arithmean_in_tick_space() -> None:
    """Verify analytically: for ticks t1, t2 with equal weight,
    TWAP price = 1.0001^((t1+t2)/2)."""
    o = TwapOracle(initial_price=1.0, lambda_blocks=2)  # initial tick = 0
    target_price = 1.0001**100  # tick = 100
    o.update(target_price, block=1)
    # Window: ticks [0, 100], weights ~equal ⇒ avg tick ≈ 50
    expected = 1.0001**50
    assert math.isclose(o.read(), expected, rel_tol=0.02)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_make_oracle_dispatches_correctly() -> None:
    o_chain = make_oracle("chainlink", initial_price=100.0)
    assert isinstance(o_chain, ExogenousOracle)

    o_twap = make_oracle("uniswap_twap", initial_price=100.0, lambda_blocks=30)
    assert isinstance(o_twap, TwapOracle)

    with pytest.raises(ValueError):
        make_oracle("nonexistent", initial_price=100.0)
