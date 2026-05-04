"""Oracle price model — exogenous and endogenous regimes.

Two regimes from `docs/SCENARIOS.md §2.3`:

- **Exogenous**: oracle price is an externally-supplied path. Liquidator
  selling does not affect the oracle. Default for off-chain feeds (Chainlink,
  Pyth) where price aggregation happens off-chain.

- **Endogenous**: oracle price is derived from on-chain DEX state, so
  liquidator selling moves it. Modeled as a TWAP over `lambda` blocks.
  Default for `uniswap_twap` markets.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from morpho_stress.models.constants import EPS


class Oracle(Protocol):
    """Common interface for all oracle models."""

    def update(self, market_price: float, block: int) -> None:
        """Feed in the latest market price observation for the block."""

    def read(self) -> float:
        """Return the current oracle-reported price."""


@dataclass
class ExogenousOracle:
    """Oracle that mirrors the externally-set market price.

    For Chainlink-like feeds: the contract reads a price published by
    off-chain aggregators. We model this as the oracle = market path with no
    liquidator feedback.
    """

    initial_price: float
    _current: float = 0.0  # set in __post_init__

    def __post_init__(self) -> None:
        if self.initial_price <= 0:
            raise ValueError("initial price must be positive")
        # __setattr__ via object since dataclass is not frozen
        self._current = self.initial_price

    def update(self, market_price: float, block: int) -> None:
        if market_price > 0:
            self._current = market_price

    def read(self) -> float:
        return self._current


class TwapOracle:
    """TWAP-smoothed oracle over a window of `lambda` blocks.

    Used as a stand-in for Uniswap v3 TWAP feeds. The endogenous regime is
    activated by feeding it the post-impact market price each block.

    Implementation: sliding window of price observations. The reported price
    is the simple mean over the window (true Uniswap TWAP is geometric mean
    on tick observations; we approximate with arithmetic for simplicity).
    A v1 extension would use the geometric mean to match Uniswap exactly.
    """

    def __init__(self, initial_price: float, lambda_blocks: int) -> None:
        if initial_price <= 0:
            raise ValueError("initial price must be positive")
        if lambda_blocks < 1:
            raise ValueError("lambda must be >= 1")
        self._lambda = lambda_blocks
        self._buffer: deque[float] = deque([initial_price], maxlen=lambda_blocks)

    def update(self, market_price: float, block: int) -> None:
        if market_price > 0:
            self._buffer.append(market_price)

    def read(self) -> float:
        if not self._buffer:
            return 0.0
        # Arithmetic mean over the window
        n = len(self._buffer)
        if n == 0:
            return 0.0
        s = sum(self._buffer)
        return s / n


def make_oracle(kind: str, initial_price: float, lambda_blocks: int = 60) -> Oracle:
    """Factory: return the appropriate oracle for a market's `oracle_kind`.

    kind ∈ {"chainlink", "pyth", "redstone", "composite"} → exogenous
    kind == "uniswap_twap" → TwapOracle
    """
    if kind in {"chainlink", "pyth", "redstone", "composite"}:
        return ExogenousOracle(initial_price=initial_price)
    if kind == "uniswap_twap":
        return TwapOracle(initial_price=initial_price, lambda_blocks=lambda_blocks)
    raise ValueError(f"unknown oracle kind: {kind}")
