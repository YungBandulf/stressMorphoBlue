"""Generate price fixtures for the 3 backtest events.

This script writes hourly oracle and market price series for each event,
calibrated to publicly-documented event characteristics:

- KelpDAO 2026-04-20: rsETH ~25% drop over ~4h around 14:00 UTC, partial
  recovery to ~88% of pre-event price by end of window.
- USDC depeg 2023-03-11: USDC trades 0.97 → 0.88 → 0.94 over ~24h around the
  SVB news cycle. Oracle (Chainlink) lags; Curve / Uniswap reflect spot.
- stETH discount 2022-05-12: stETH/ETH ratio 0.99 → 0.94 over 5 days as
  Terra/UST collapse triggers withdrawal queue concerns.

The synthetic paths are NOT exact replays of every tick; they reflect the
documented shape of each event, with hourly cadence and noise level matching
historical observations.

References:
- KelpDAO: rekt.news, Aave governance post-mortem
- USDC depeg: Circle blog 2023-03-11, CoinGecko historical USDC/USD
- stETH discount: Curve.fi historical pool composition, Lido blog

Run:
    PYTHONPATH=src python data/fixtures/_generate_prices.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


HERE = Path(__file__).parent


def _hourly_range(start: datetime, end: datetime) -> list[datetime]:
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(hours=1)
    return out


def kelpdao_prices() -> pd.DataFrame:
    """rsETH price path: ~25% drop over 4h on 2026-04-20 ~14:00 UTC."""
    start = datetime(2026, 4, 15, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 25, 0, 0, tzinfo=timezone.utc)
    timestamps = _hourly_range(start, end)
    n = len(timestamps)

    pre_event_price = 3142.50
    rng = np.random.default_rng(20260420)

    # Pre-event: small drift around 3140 with minor noise
    base = np.full(n, pre_event_price)
    noise = rng.normal(0.0, 0.003, n) * pre_event_price
    base = base + noise

    # Event impact: between hour 14:00 UTC of 2026-04-20 and hour 18:00 UTC,
    # apply a sharp drawdown to ~75% of pre-event, then partial recovery.
    event_start = datetime(2026, 4, 20, 13, 0, tzinfo=timezone.utc)
    floor_time = datetime(2026, 4, 20, 18, 0, tzinfo=timezone.utc)
    recovery_end = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)

    floor_price = pre_event_price * 0.75
    recovery_price = pre_event_price * 0.88

    for i, ts in enumerate(timestamps):
        if ts < event_start:
            continue
        elif event_start <= ts <= floor_time:
            # Linear drawdown
            frac = (ts - event_start).total_seconds() / (floor_time - event_start).total_seconds()
            base[i] = pre_event_price * (1.0 - 0.25 * frac) + rng.normal(0.0, 30.0)
        elif floor_time < ts <= recovery_end:
            frac = (ts - floor_time).total_seconds() / (recovery_end - floor_time).total_seconds()
            base[i] = floor_price + (recovery_price - floor_price) * frac + rng.normal(0.0, 30.0)
        else:
            base[i] = recovery_price + rng.normal(0.0, 25.0)

    # Oracle (Chainlink) follows market with ~10 min effective lag, smoothed
    # via simple EMA in this fixture (real Chainlink has heartbeat + deviation
    # threshold, but for fixture purposes EMA captures the lag effect).
    oracle = np.empty(n)
    oracle[0] = base[0]
    alpha = 0.5  # EMA factor, ~equivalent to 1-2h smoothing at hourly cadence
    for i in range(1, n):
        oracle[i] = alpha * base[i] + (1 - alpha) * oracle[i - 1]

    rows = []
    for i, ts in enumerate(timestamps):
        rows.append(
            {
                "ts": ts.isoformat().replace("+00:00", "Z"),
                "symbol": "rsETH",
                "market_price_usd": round(float(base[i]), 2),
                "oracle_price_usd": round(float(oracle[i]), 2),
                "source": "fixture:kelpdao_post_mortem_v1",
            }
        )
    return pd.DataFrame(rows)


def usdc_depeg_prices() -> pd.DataFrame:
    """USDC/USD path: 0.97 → 0.88 → 0.94 over 2023-03-10 to 2023-03-13."""
    start = datetime(2023, 3, 8, 0, 0, tzinfo=timezone.utc)
    end = datetime(2023, 3, 17, 0, 0, tzinfo=timezone.utc)
    timestamps = _hourly_range(start, end)
    n = len(timestamps)

    rng = np.random.default_rng(20230311)

    # Stages of the depeg:
    # Pre 2023-03-10 18:00: stable at 1.000
    # 2023-03-10 18:00 → 2023-03-11 04:00: 1.000 → 0.95 (initial reaction to SVB news)
    # 2023-03-11 04:00 → 2023-03-11 12:00: 0.95 → 0.88 (panic low)
    # 2023-03-11 12:00 → 2023-03-13 00:00: 0.88 → 0.97 (Fed bail of SVB depositors)
    # 2023-03-13 00:00 → end: 0.97 → 1.000

    market = np.full(n, 1.000)
    pre_event = datetime(2023, 3, 10, 18, 0, tzinfo=timezone.utc)
    initial_drop_end = datetime(2023, 3, 11, 4, 0, tzinfo=timezone.utc)
    panic_low = datetime(2023, 3, 11, 12, 0, tzinfo=timezone.utc)
    fed_announce = datetime(2023, 3, 13, 0, 0, tzinfo=timezone.utc)

    for i, ts in enumerate(timestamps):
        if ts < pre_event:
            market[i] = 1.000
        elif pre_event <= ts <= initial_drop_end:
            frac = (ts - pre_event).total_seconds() / (initial_drop_end - pre_event).total_seconds()
            market[i] = 1.000 - 0.05 * frac
        elif initial_drop_end < ts <= panic_low:
            frac = (ts - initial_drop_end).total_seconds() / (panic_low - initial_drop_end).total_seconds()
            market[i] = 0.95 - 0.07 * frac
        elif panic_low < ts <= fed_announce:
            frac = (ts - panic_low).total_seconds() / (fed_announce - panic_low).total_seconds()
            market[i] = 0.88 + 0.09 * frac
        else:
            market[i] = 0.97 + min(0.03, (ts - fed_announce).total_seconds() / 86400 * 0.01)

        market[i] += rng.normal(0.0, 0.002)

    # Oracle: Chainlink USDC has heartbeat 24h, deviation 0.25%, but in 2023
    # the feed effectively held at 1.0 for hours during the depeg until pulled
    # off-chain. We model oracle = clipped slow EMA, capped at 1.0.
    oracle = np.full(n, 1.000)
    for i in range(1, n):
        # Slow EMA, capped at 1.0
        oracle[i] = min(1.0, 0.95 * oracle[i - 1] + 0.05 * market[i])

    rows = []
    for i, ts in enumerate(timestamps):
        rows.append(
            {
                "ts": ts.isoformat().replace("+00:00", "Z"),
                "symbol": "USDC",
                "market_price_usd": round(float(market[i]), 4),
                "oracle_price_usd": round(float(oracle[i]), 4),
                "source": "fixture:usdc_depeg_chainlink_archive",
            }
        )
    return pd.DataFrame(rows)


def steth_discount_prices() -> pd.DataFrame:
    """stETH/ETH ratio: 0.99 → 0.94 over 2022-05-09 to 2022-05-14."""
    start = datetime(2022, 5, 7, 0, 0, tzinfo=timezone.utc)
    end = datetime(2022, 5, 17, 0, 0, tzinfo=timezone.utc)
    timestamps = _hourly_range(start, end)
    n = len(timestamps)

    rng = np.random.default_rng(20220512)

    eth_usd = 2050.0  # approximate ETH price during the window
    pre_ratio = 0.995  # stETH was already at slight discount pre-Terra
    discount_low_ratio = 0.94

    discount_start = datetime(2022, 5, 9, 12, 0, tzinfo=timezone.utc)
    discount_low = datetime(2022, 5, 12, 9, 0, tzinfo=timezone.utc)

    market_steth_eth = np.full(n, pre_ratio)
    for i, ts in enumerate(timestamps):
        if ts < discount_start:
            market_steth_eth[i] = pre_ratio
        elif discount_start <= ts <= discount_low:
            frac = (ts - discount_start).total_seconds() / (discount_low - discount_start).total_seconds()
            market_steth_eth[i] = pre_ratio + (discount_low_ratio - pre_ratio) * frac
        else:
            # Slow recovery to ~0.97 by end of window
            frac = (ts - discount_low).total_seconds() / (end - discount_low).total_seconds()
            market_steth_eth[i] = discount_low_ratio + (0.97 - discount_low_ratio) * frac

        market_steth_eth[i] += rng.normal(0.0, 0.002)

    market_price = market_steth_eth * eth_usd

    # Oracle: at the time, Aave used Chainlink stETH/ETH which was relatively
    # accurate (low staleness). We model oracle ≈ market with light EMA.
    oracle = np.empty(n)
    oracle[0] = market_price[0]
    alpha = 0.7
    for i in range(1, n):
        oracle[i] = alpha * market_price[i] + (1 - alpha) * oracle[i - 1]

    rows = []
    for i, ts in enumerate(timestamps):
        rows.append(
            {
                "ts": ts.isoformat().replace("+00:00", "Z"),
                "symbol": "stETH",
                "market_price_usd": round(float(market_price[i]), 2),
                "oracle_price_usd": round(float(oracle[i]), 2),
                "source": "fixture:steth_curve_archive_v1",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    out = {
        "kelpdao_2026_04": kelpdao_prices(),
        "usdc_depeg_2023_03": usdc_depeg_prices(),
        "steth_discount_2022_05": steth_discount_prices(),
    }
    for event_id, df in out.items():
        path = HERE / event_id / "prices.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        print(f"wrote {len(df)} rows to {path}")


if __name__ == "__main__":
    main()
