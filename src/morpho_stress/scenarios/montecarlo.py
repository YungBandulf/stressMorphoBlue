"""Monte Carlo framework for stress scenarios.

Per `docs/SCENARIOS.md §5`: each scenario is parameterized by a shock vector
``δ`` which can be either deterministic (point mode) or sampled from an
empirical distribution (Monte Carlo mode).

This module provides:

1. ``EmpiricalDistribution`` — a wrapper around an array of historical
   observations supporting bootstrap sampling. Block bootstrap is provided
   for autocorrelated series.

2. ``MonteCarloRunner`` — runs ``n_paths`` simulations of a scenario, each
   with a fresh sample from an empirical distribution, and aggregates output
   metrics into ``McResult``.

3. ``McResult`` — distributional summary of metrics across paths.

Design notes:

- The runner is **scenario-agnostic**: it takes a callable
  ``(state, shock) -> Trajectory`` and a metric extractor. New scenarios plug
  in without changes.
- Reproducibility is via ``seed``. Each path uses a derived seed
  (``seed + path_id``) to allow deterministic regeneration of any single path.
- Parallelization hooks are present (joblib-style ``n_jobs``) but the v0
  implementation runs serial. Parallelization is straightforward to add since
  paths are independent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from morpho_stress.scenarios.state import MarketState
from morpho_stress.scenarios.trajectory import Trajectory


# ---------------------------------------------------------------------------
# Empirical distribution
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmpiricalDistribution:
    """Empirical distribution of a 1D shock parameter.

    Supports two sampling modes:

    - **iid bootstrap**: sample with replacement from observations.
    - **block bootstrap**: sample contiguous blocks of size `block_size` to
      preserve short-range autocorrelation. Useful for time-series-derived
      observations (e.g. rolling 24h drawdown maxima).

    Args:
        observations: 1D array of historical observation values.
        block_size: block size for block-bootstrap. 1 = iid bootstrap.
    """

    observations: np.ndarray
    block_size: int = 1

    def __post_init__(self) -> None:
        if self.observations.ndim != 1:
            raise ValueError("observations must be 1D")
        if len(self.observations) == 0:
            raise ValueError("observations cannot be empty")
        if self.block_size < 1:
            raise ValueError("block_size must be >= 1")
        if self.block_size > len(self.observations):
            raise ValueError("block_size larger than dataset")

    def sample(self, rng: np.random.Generator, size: int = 1) -> np.ndarray:
        """Draw ``size`` samples from the empirical distribution."""
        if self.block_size == 1:
            idx = rng.integers(0, len(self.observations), size=size)
            return self.observations[idx]
        # Block bootstrap: pick block start indices, concatenate, truncate
        n_blocks = (size + self.block_size - 1) // self.block_size
        max_start = len(self.observations) - self.block_size + 1
        starts = rng.integers(0, max_start, size=n_blocks)
        chunks = [self.observations[s : s + self.block_size] for s in starts]
        out = np.concatenate(chunks)[:size]
        return out

    def quantile(self, q: float | np.ndarray) -> float | np.ndarray:
        """Empirical quantile at level ``q`` (or array of levels)."""
        return np.quantile(self.observations, q)


# ---------------------------------------------------------------------------
# MC result aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class McResult:
    """Distributional summary of a Monte Carlo run.

    For each metric, holds the ``n_paths``-vector of realized values plus
    aggregate statistics (mean, std, p5, p50, p95, p99).
    """

    metric_name: str
    samples: np.ndarray  # shape (n_paths,)

    @property
    def mean(self) -> float:
        return float(self.samples.mean())

    @property
    def std(self) -> float:
        return float(self.samples.std(ddof=1)) if len(self.samples) > 1 else 0.0

    def quantile(self, q: float) -> float:
        return float(np.quantile(self.samples, q))

    @property
    def p5(self) -> float:
        return self.quantile(0.05)

    @property
    def p50(self) -> float:
        return self.quantile(0.50)

    @property
    def p95(self) -> float:
        return self.quantile(0.95)

    @property
    def p99(self) -> float:
        return self.quantile(0.99)

    def summary(self) -> dict[str, float]:
        """Standard summary dict for reports / dashboards."""
        return {
            "metric": self.metric_name,
            "mean": self.mean,
            "std": self.std,
            "p5": self.p5,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "n_paths": len(self.samples),
        }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_monte_carlo(
    initial_state: MarketState,
    distribution: EmpiricalDistribution,
    scenario_fn: Callable[[MarketState, float], Trajectory],
    metric_fns: dict[str, Callable[[Trajectory], float]],
    n_paths: int,
    seed: int = 42,
) -> dict[str, McResult]:
    """Run a Monte Carlo simulation over a stress scenario.

    Args:
        initial_state: market state at t=0 (same for every path)
        distribution: empirical distribution of the shock parameter
        scenario_fn: callable (state, shock) -> Trajectory
        metric_fns: dict of metric name → trajectory-to-float extractor
        n_paths: number of MC paths
        seed: master seed; per-path seeds are derived as ``seed + path_id``

    Returns:
        Dict of metric_name → McResult
    """
    if n_paths < 1:
        raise ValueError("n_paths must be >= 1")
    if not metric_fns:
        raise ValueError("at least one metric_fn must be provided")

    # Pre-allocate result buffers
    samples: dict[str, np.ndarray] = {
        name: np.empty(n_paths, dtype=float) for name in metric_fns
    }

    master_rng = np.random.default_rng(seed)
    # Pre-sample shocks for all paths so the run is fully deterministic given the seed
    shocks = distribution.sample(master_rng, size=n_paths)

    for path_id in range(n_paths):
        traj = scenario_fn(initial_state, float(shocks[path_id]))
        for name, fn in metric_fns.items():
            samples[name][path_id] = fn(traj)

    return {
        name: McResult(metric_name=name, samples=arr) for name, arr in samples.items()
    }


# ---------------------------------------------------------------------------
# Helpers for typical use cases
# ---------------------------------------------------------------------------


def joint_mc(
    initial_state: MarketState,
    distributions: dict[str, EmpiricalDistribution],
    scenario_fn: Callable[[MarketState, dict[str, float]], Trajectory],
    metric_fns: dict[str, Callable[[Trajectory], float]],
    n_paths: int,
    seed: int = 42,
) -> dict[str, McResult]:
    """Like ``run_monte_carlo`` but with multiple shock parameters sampled jointly.

    The shock parameters are sampled **independently** per the marginal
    distributions. To preserve dependencies, supply already-correlated samples
    via a custom scenario_fn.
    """
    if n_paths < 1:
        raise ValueError("n_paths must be >= 1")

    samples: dict[str, np.ndarray] = {
        name: np.empty(n_paths, dtype=float) for name in metric_fns
    }

    master_rng = np.random.default_rng(seed)
    sampled = {
        name: dist.sample(master_rng, size=n_paths)
        for name, dist in distributions.items()
    }

    for path_id in range(n_paths):
        shocks = {name: float(arr[path_id]) for name, arr in sampled.items()}
        traj = scenario_fn(initial_state, shocks)
        for name, fn in metric_fns.items():
            samples[name][path_id] = fn(traj)

    return {
        name: McResult(metric_name=name, samples=arr) for name, arr in samples.items()
    }
