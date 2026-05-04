"""Tests for the Monte Carlo framework."""

from __future__ import annotations

import math

import numpy as np
import pytest

from morpho_stress.models.slippage import SlippageCurve
from morpho_stress.scenarios import (
    EmpiricalDistribution,
    S1Config,
    S3Config,
    n_liquidated,
    run_monte_carlo,
    stress_s1,
    stress_s3,
    total_bad_debt,
)
from morpho_stress.scenarios.trajectory import Trajectory
from morpho_stress.utils.mock import make_market_state


# ---------------------------------------------------------------------------
# Empirical distribution
# ---------------------------------------------------------------------------


def test_empirical_distribution_iid_bootstrap() -> None:
    obs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    dist = EmpiricalDistribution(observations=obs)
    rng = np.random.default_rng(42)
    samples = dist.sample(rng, size=1000)
    # Mean should converge to true mean of [1,2,3,4,5] = 3.0
    assert math.isclose(samples.mean(), 3.0, abs_tol=0.2)
    # All samples must be in the original observation set
    assert set(np.unique(samples)).issubset(set(obs))


def test_empirical_distribution_block_bootstrap() -> None:
    """Block bootstrap of size 5 must produce contiguous chunks of 5."""
    obs = np.arange(100, dtype=float)
    dist = EmpiricalDistribution(observations=obs, block_size=5)
    rng = np.random.default_rng(42)
    samples = dist.sample(rng, size=20)
    # First 5 samples must be contiguous integers
    block1 = samples[:5]
    diffs = np.diff(block1)
    assert all(d == 1.0 for d in diffs)


def test_empirical_distribution_quantile() -> None:
    obs = np.linspace(0.0, 1.0, 101)
    dist = EmpiricalDistribution(observations=obs)
    assert math.isclose(dist.quantile(0.5), 0.5, abs_tol=1e-9)
    assert math.isclose(dist.quantile(0.99), 0.99, abs_tol=1e-9)


def test_empirical_distribution_validates_inputs() -> None:
    with pytest.raises(ValueError):
        EmpiricalDistribution(observations=np.array([]))
    with pytest.raises(ValueError):
        EmpiricalDistribution(observations=np.array([[1, 2], [3, 4]], dtype=float))
    with pytest.raises(ValueError):
        EmpiricalDistribution(observations=np.array([1.0, 2.0]), block_size=0)
    with pytest.raises(ValueError):
        EmpiricalDistribution(observations=np.array([1.0, 2.0]), block_size=5)


# ---------------------------------------------------------------------------
# MC runner — S1
# ---------------------------------------------------------------------------


def test_mc_runner_s1_deterministic_with_seed() -> None:
    """Same seed ⇒ same results."""
    state = make_market_state()
    obs = np.array([0.05, 0.1, 0.15, 0.2, 0.25, 0.3])
    dist = EmpiricalDistribution(observations=obs)

    def scenario(s, alpha):
        return stress_s1(
            s, S1Config(alpha=alpha, duration_blocks=300, horizon_blocks=300)
        )

    metrics = {
        "queued": lambda t: t.final_state.queued_withdrawals,
    }

    r1 = run_monte_carlo(state, dist, scenario, metrics, n_paths=20, seed=42)
    r2 = run_monte_carlo(state, dist, scenario, metrics, n_paths=20, seed=42)
    assert np.allclose(r1["queued"].samples, r2["queued"].samples)


def test_mc_runner_s1_different_seeds_differ() -> None:
    state = make_market_state()
    obs = np.array([0.05, 0.1, 0.15, 0.2, 0.25, 0.3])
    dist = EmpiricalDistribution(observations=obs)

    def scenario(s, alpha):
        return stress_s1(
            s, S1Config(alpha=alpha, duration_blocks=300, horizon_blocks=300)
        )

    metrics = {"queued": lambda t: t.final_state.queued_withdrawals}

    r1 = run_monte_carlo(state, dist, scenario, metrics, n_paths=20, seed=1)
    r2 = run_monte_carlo(state, dist, scenario, metrics, n_paths=20, seed=2)
    # With different seeds, the sequences differ
    assert not np.allclose(r1["queued"].samples, r2["queued"].samples)


def test_mc_result_aggregates() -> None:
    state = make_market_state()
    obs = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    dist = EmpiricalDistribution(observations=obs)

    def scenario(s, alpha):
        return stress_s1(
            s, S1Config(alpha=alpha, duration_blocks=300, horizon_blocks=300)
        )

    metrics = {"queued": lambda t: t.final_state.queued_withdrawals}
    results = run_monte_carlo(state, dist, scenario, metrics, n_paths=100, seed=42)
    res = results["queued"]
    assert res.p5 <= res.p50 <= res.p95 <= res.p99
    assert res.std >= 0
    summary = res.summary()
    assert summary["n_paths"] == 100


# ---------------------------------------------------------------------------
# MC runner — S3
# ---------------------------------------------------------------------------


def test_mc_runner_s3() -> None:
    state = make_market_state()
    curve = SlippageCurve(asset_symbol="WETH", a=2e-4, b=0.55)
    drawdown_obs = np.array([0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35])
    dist = EmpiricalDistribution(observations=drawdown_obs)

    def scenario(s, drawdown):
        return stress_s3(
            s,
            S3Config(drawdown=drawdown, dt_blocks=20, horizon_blocks=30),
            curve,
        )

    metrics = {
        "n_liquidated": lambda t: float(n_liquidated(t)),
        "bad_debt": total_bad_debt,
    }

    results = run_monte_carlo(state, dist, scenario, metrics, n_paths=30, seed=42)
    assert results["n_liquidated"].mean >= 0
    assert results["bad_debt"].mean >= 0
    # Bad debt p99 should be >= mean
    assert results["bad_debt"].p99 >= results["bad_debt"].mean - 1e-9


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_mc_runner_invalid_n_paths() -> None:
    state = make_market_state()
    dist = EmpiricalDistribution(observations=np.array([0.1]))

    def scenario(s, x) -> Trajectory:
        return Trajectory(states=[s])

    with pytest.raises(ValueError):
        run_monte_carlo(state, dist, scenario, {"x": lambda t: 0.0}, n_paths=0)


def test_mc_runner_no_metrics() -> None:
    state = make_market_state()
    dist = EmpiricalDistribution(observations=np.array([0.1]))

    def scenario(s, x) -> Trajectory:
        return Trajectory(states=[s])

    with pytest.raises(ValueError):
        run_monte_carlo(state, dist, scenario, {}, n_paths=5)
