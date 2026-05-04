"""Mock data generator for Morpho Blue markets.

Produces synthetic states, positions, and DEX slippage observations that
respect Morpho Blue's invariants:

- total_borrow_assets <= total_supply_assets
- per-position LTV <= LLTV at construction time
- positions sum to total_collateral and total_borrow_shares
- monotonically increasing block timestamps

Used to test scenario logic and modeling code without RPC dependency.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from morpho_stress.scenarios.state import MarketParams, MarketState, Position


def _addr(seed: int, idx: int) -> str:
    """Deterministic synthetic address for testing."""
    raw = (seed * 0x10000 + idx) % (1 << 160)
    return "0x" + f"{raw:040x}"


def make_market_params(
    market_id: str | None = None,
    lltv: float = 0.86,
    fee: float = 0.0,
    oracle_kind: str = "chainlink",
) -> MarketParams:
    """Create a default Morpho Blue market params object."""
    if market_id is None:
        market_id = "0x" + "ab" * 32
    return MarketParams(
        market_id=market_id,
        loan_decimals=6,  # USDC default
        collateral_decimals=18,  # WETH/wstETH default
        lltv=lltv,
        fee=fee,
        oracle_kind=oracle_kind,
    )


def make_market_state(
    initial_supply: float = 100_000_000.0,  # 100M USDC
    utilization: float = 0.85,
    oracle_price: float = 2_000.0,  # 1 WETH = 2000 USDC, classic
    n_positions: int = 50,
    avg_ltv: float = 0.7,
    ltv_std: float = 0.1,
    rate_at_target: float = 0.04,
    seed: int = 42,
    params: MarketParams | None = None,
) -> MarketState:
    """Build a synthetic market state with consistent positions.

    Generates `n_positions` borrowers with LTVs sampled from
    Beta-like distribution centered on `avg_ltv`, capped at LLTV - 1bp to
    ensure the initial state has no liquidatable positions.
    """
    rng = np.random.default_rng(seed)
    params = params or make_market_params()

    total_supply = initial_supply
    total_borrow = total_supply * utilization

    # Sample per-position borrow weights (proportional to share of total borrow)
    weights = rng.dirichlet(np.ones(n_positions))
    pos_borrow_assets = total_borrow * weights

    # Sample per-position LTV, capped strictly below LLTV
    raw_ltvs = rng.normal(avg_ltv, ltv_std, n_positions)
    cap = params.lltv - 1e-4
    ltvs = np.clip(raw_ltvs, 0.05, cap)

    # collateral = borrow / (ltv * price)
    pos_collateral = pos_borrow_assets / (ltvs * oracle_price)

    # Shares accounting: 1 share = 1 asset at construction (clean state)
    total_borrow_shares = total_borrow
    pos_borrow_shares = pos_borrow_assets  # 1:1 ratio at t=0

    positions = tuple(
        Position(
            borrower=_addr(seed, i),
            collateral=float(pos_collateral[i]),
            borrow_shares=float(pos_borrow_shares[i]),
        )
        for i in range(n_positions)
    )

    total_collateral = float(pos_collateral.sum())

    return MarketState(
        params=params,
        block=21_900_000,
        block_ts=1_746_000_000,  # ~ May 2026
        total_supply_assets=total_supply,
        total_supply_shares=total_supply,  # 1:1 at construction
        total_borrow_assets=total_borrow,
        total_borrow_shares=total_borrow_shares,
        total_collateral=total_collateral,
        oracle_price=oracle_price,
        rate_at_target=rate_at_target,
        positions=positions,
    )


def make_dex_slippage_observations(
    asset_symbol: str = "wstETH",
    n_observations: int = 100,
    a_true: float = 1e-4,
    b_true: float = 0.55,
    noise_bps: float = 5.0,
    seed: int = 42,
    oracle_price: float = 2_000.0,
) -> pd.DataFrame:
    """Generate synthetic DEX slippage observations with known (a, b).

    Used to test the slippage curve fitter.
    """
    rng = np.random.default_rng(seed)

    # Volume in native units, log-uniform over 4 decades
    volumes = np.exp(rng.uniform(0, 4 * np.log(10), n_observations))
    pi_true = a_true * volumes**b_true
    # Multiplicative log-normal noise
    log_noise = rng.normal(0.0, noise_bps / 1e4, n_observations)
    pi_observed = np.clip(pi_true * np.exp(log_noise), 1e-6, 0.5)

    realized_prices = oracle_price * (1.0 - pi_observed)
    slippage_bps = pi_observed * 10_000.0

    return pd.DataFrame(
        {
            "collateral_symbol": asset_symbol,
            "quote_ts": pd.date_range(
                "2025-05-01", periods=n_observations, freq="1h", tz="UTC"
            ),
            "direction": "sell_collateral_for_loan",
            "volume_usd": volumes * oracle_price,
            "volume_native": volumes,
            "oracle_price": oracle_price,
            "realized_price": realized_prices,
            "slippage_bps": slippage_bps,
            "source": "1inch_quote",
        }
    )
