"""Oracle price models — exogenous and Uniswap-V3-style geometric TWAP.

Two regimes from `docs/SCENARIOS.md §2.3`:

- **Exogenous**: oracle price is an externally-supplied path. Liquidator
  selling does not affect the oracle. Default for off-chain feeds (Chainlink,
  Pyth) where price aggregation happens off-chain.

- **Endogenous (Uniswap V3 TWAP)**: oracle price is the geometric mean of
  observed market prices over a window of ``lambda`` blocks. Implemented
  faithful to Uniswap V3:

      price = 1.0001 ** (cumulative_tick_delta / time_delta)

  where ``tick = log_{1.0001}(price)`` and the cumulative tick is summed
  across observations. This is the geometric mean in the price domain.

Reference:
    Uniswap V3 Core, ``OracleLibrary.consult`` and ``Tick.observeSingle``.
    https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/Oracle.sol
    https://docs.uniswap.org/concepts/protocol/oracle
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from morpho_stress.models.constants import EPS

# Uniswap V3 tick base
TICK_BASE = 1.0001
LOG_TICK_BASE = math.log(TICK_BASE)


def price_to_tick(price: float) -> float:
    """Convert price to Uniswap V3 tick: tick = log_{1.0001}(price).

    Returns float, not int, because we do not need exact tick alignment for
    aggregate TWAP; we work in continuous tick space.
    """
    if price <= 0:
        raise ValueError(f"price must be positive: {price}")
    return math.log(price) / LOG_TICK_BASE


def tick_to_price(tick: float) -> float:
    """Convert tick back to price: price = 1.0001 ^ tick."""
    return math.exp(tick * LOG_TICK_BASE)


class Oracle(Protocol):
    """Common interface for all oracle models."""

    def update(self, market_price: float, block: int) -> None:
        """Feed in the latest market price observation for the given block."""

    def read(self) -> float:
        """Return the current oracle-reported price."""


@dataclass
class ExogenousOracle:
    """Oracle that mirrors the externally-set market price.

    For Chainlink-like feeds: the contract reads a price published by
    off-chain aggregators. We model this as the oracle = market path, with no
    liquidator feedback.
    """

    initial_price: float
    _current: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_price <= 0:
            raise ValueError("initial price must be positive")
        self._current = self.initial_price

    def update(self, market_price: float, block: int) -> None:
        if market_price > 0:
            self._current = market_price

    def read(self) -> float:
        return self._current


class TwapOracle:
    """Uniswap V3-style geometric TWAP over a window of ``lambda`` blocks.

    Implementation:

    1. Each ``update(price, block)`` records a ``(block, tick)`` observation,
       where ``tick = log_{1.0001}(price)``.
    2. ``read()`` returns the geometric mean of prices across the observation
       window:

           tick_avg = (sum_i tick_i × dt_i) / total_dt
           price_twap = 1.0001 ** tick_avg

       where ``dt_i`` is the time interval each tick was active. This matches
       Uniswap V3's ``observeSingle`` semantics: cumulative tick is the
       integral of tick over time, so the average is the time-weighted mean
       in tick (equivalently log-price) space.

    For simplicity, we assume observations come at every block (constant
    ``dt = 1``) when used in the simulation pipeline. The implementation
    accepts non-constant ``dt`` for general use.

    The geometric mean is the right average for prices because compounded
    returns are additive in log-space — this is also why Uniswap V3 chose it.

    Args:
        initial_price: bootstrapping price (window starts here).
        lambda_blocks: window size in blocks. Must be ≥ 1.
    """

    def __init__(self, initial_price: float, lambda_blocks: int) -> None:
        if initial_price <= 0:
            raise ValueError("initial price must be positive")
        if lambda_blocks < 1:
            raise ValueError("lambda must be >= 1")
        self._lambda = lambda_blocks
        # Each observation: (block, tick). dt is implicit (next.block - this.block);
        # the most recent observation has dt = 1 conceptually until the next update.
        initial_tick = price_to_tick(initial_price)
        self._obs: deque[tuple[int, float]] = deque(maxlen=lambda_blocks)
        self._obs.append((0, initial_tick))

    def update(self, market_price: float, block: int) -> None:
        if market_price <= 0:
            return
        tick = price_to_tick(market_price)
        self._obs.append((block, tick))

    def read(self) -> float:
        """Return the geometric-mean price over the observation window.

        If the window contains a single observation, returns its price.
        """
        if not self._obs:
            return 0.0
        n = len(self._obs)
        if n == 1:
            return tick_to_price(self._obs[0][1])

        # Compute time-weighted mean of ticks.
        # Each obs[i] has weight (obs[i+1].block - obs[i].block); the last obs
        # has implicit weight 1 (it has been the prevailing tick for at least
        # one block since being recorded, which is a defensible default).
        total_weight = 0.0
        weighted_sum = 0.0
        obs_list = list(self._obs)
        for i in range(n - 1):
            block_i, tick_i = obs_list[i]
            block_next = obs_list[i + 1][0]
            dt = max(1, block_next - block_i)
            weighted_sum += tick_i * dt
            total_weight += dt
        # Last observation: weight 1
        _, last_tick = obs_list[-1]
        weighted_sum += last_tick * 1
        total_weight += 1

        if total_weight < EPS:
            return tick_to_price(last_tick)

        avg_tick = weighted_sum / total_weight
        return tick_to_price(avg_tick)


def make_oracle(kind: str, initial_price: float, lambda_blocks: int = 60) -> Oracle:
    """Factory: return the appropriate oracle for a market's ``oracle_kind``.

    kind ∈ {"chainlink", "pyth", "redstone", "composite"} → ExogenousOracle
    kind == "uniswap_twap" → TwapOracle
    """
    if kind in {"chainlink", "pyth", "redstone", "composite"}:
        return ExogenousOracle(initial_price=initial_price)
    if kind == "uniswap_twap":
        return TwapOracle(initial_price=initial_price, lambda_blocks=lambda_blocks)
    raise ValueError(f"unknown oracle kind: {kind}")
