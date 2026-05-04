"""Numerical constants used across the framework."""

from __future__ import annotations

# Numerical tolerance for floating-point comparisons.
# Picked to be 1e-9 of typical USD notionals (~1e9 USD) ⇒ ~1 atto-USD.
EPS = 1e-9

# Ethereum block time, in seconds. Post-merge constant.
BLOCK_TIME_SEC = 12

# Year in seconds, used for IRM rate accrual.
SECONDS_PER_YEAR = 365 * 24 * 3600

# Liquidation incentive (Morpho Blue formula): max(1.0 + 0.15 * (1/LLTV - 1), 1.15)
# The actual on-chain incentive depends on LLTV; computed in the liquidation engine.
DEFAULT_LIQUIDATION_INCENTIVE = 1.05  # 5% bonus, conservative default

# Reorg buffer for RPC reads.
REORG_BUFFER_BLOCKS = 32
