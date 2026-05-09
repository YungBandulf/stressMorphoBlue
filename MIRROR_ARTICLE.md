# A Liquidity Stress Test for Morpho Blue, Adapted from Basel III

**A reproducible, falsifiable risk framework applied to 26 live Ethereum mainnet markets.**

---

## Why this matters

Decentralised-finance lending protocols hold tens of billions of dollars of deposits, and their fragility under stress is theoretically established (Chiu, Ozdenoren, Yuan & Zhang, BIS Working Paper 1062, 2023). Yet most public risk reports for these protocols transpose Basel concepts informally, without explicit pass-or-fail criteria, and without a reproducible backtest against historical events.

This work formalises the transposition for **Morpho Blue**, the non-custodial lending protocol with isolated markets and immutable parameters. We adapt the **Liquidity Coverage Ratio** defined by the Basel Committee on Banking Supervision in BCBS 238 (2013) and apply it to live on-chain data.

The full source code, test suite, and reproducible event fixtures are open-source. All 145 tests pass; all 26 markets are evaluated from live mainnet state, no synthetic data.

---

## What we measure

For each market, three pass-or-fail criteria, all sourced from the spirit of BCBS 238:

1. **Continuous Liquidity Coverage Ratio**: probability that High-Quality Liquid Assets fall below stressed outflows under a 24-hour scenario, denoted Pr(LCR < 1).
2. **Time-to-illiquid**: hours before instant liquidity is exhausted under a calibrated outflow rate.
3. **Bad-debt magnitude**: 99th-percentile bad debt expressed as a fraction of Total Value Locked.

A market is `red` when any single component reaches red severity; `yellow` for stress-band conditions; `green-watch` for sound-but-monitor; `green-strong` for fully robust.

---

## Calibration: against history, not vibes

The framework is anchored on three historical stress events:

- **KelpDAO collateral exploit** (April 2026), the primary anchor.
- **USDC depeg** (March 2023), with -8% trough, ~25% day-one Aave outflow.
- **Staked-Ether discount episode** (May 2022), -8% trough over multiple days.

Two events PASS the framework's pre-event detection criteria. The third (stETH 2022) FAILs honestly: the framework is a 24-hour LCR test and the stETH episode was a multi-day repricing rather than an acute liquidity stress. We report this failure rather than retrofitting parameters to make it pass.

**Class-floored drawdowns** for forward-looking stress, calibrated per asset class against the events above:

- Stablecoin synthetics: 5%
- Liquid staking tokens: 8%
- Wrapped Bitcoin variants: 10%
- Pendle principal tokens: 15%
- Wrapped Ether: 8%

These minima override the empirical 99th-percentile when the observed history is shorter than the structural risk of the asset class.

---

## Methodology in one paragraph

For each market we run two stress scenarios in parallel rather than cumulating both stresses in one path. **Scenario A** combines a class-floored 99th-percentile drawdown with a moderate outflow alpha. **Scenario B** combines a typical drawdown with an amplified outflow alpha (20% to 30%, calibrated on KelpDAO and the USDC depeg). The reported LCR is the worst of the two; the bad-debt distribution comes from a Monte Carlo over the empirical drawdown distribution. Position-level loan-to-values are sampled from a Beta distribution with mean 0.65 × LLTV, capturing the right-skewed observation that most borrowers are moderately leveraged with an aggressive minority near the liquidation threshold.

---

## Findings, nominal stress

Applied to the **26 most material Morpho Blue isolated markets on Ethereum mainnet** (aggregate Total Value Locked ~$1.7B):

| Tier | Markets | TVL | Share |
|---|---|---|---|
| red | 1 | $23M | 1.4% |
| yellow | 7 | $737M | 43.5% |
| green-watch | 5 | $384M | 22.6% |
| green-strong | 13 | $552M | 32.6% |

The single **red** market is **PT-apyUSD-18JUN2026/USDC**, a Pendle principal-token market with 99th-percentile bad debt at 5.7% of TVL and 68.5% probability of positive bad debt across Monte Carlo paths. Two compounding factors: the structural illiquidity of Pendle secondary markets (slippage parameters $a = 10^{-3}$, $b = 0.65$) and a high utilisation (82.6%) that compresses the headroom available for liquidation cascades.

The **yellow** tier carries the bulk of material exposure in absolute dollar terms:

| Market | TVL | Bad-debt p99 | bd/TVL |
|---|---|---|---|
| cbBTC/USDC | $268M | $5.30M | 1.98% |
| wstETH/USDT | $218M | $4.78M | 2.19% |
| WBTC/USDC | $156M | $2.13M | 1.37% |
| wstETH/USDC | $44M | $1.05M | 2.36% |

These four mainstream BTC/ETH-collateral markets carry $686M of TVL (40% of analysed total) and roughly $13.3M of cumulative 99th-percentile bad debt.

---

## Findings, extreme stress

To probe the protocol under conditions exceeding observed history, we run a separate test: drawdown 25%, outflow alpha 35%, calibrated against the KelpDAO + USDC depeg hybrid. A market `survives` if both LCR ≥ 1.0 AND 99th-percentile bad debt < 10% TVL.

| Verdict | Markets | TVL | Share |
|---|---|---|---|
| PASS | 18 | $1,220M | 71.9% |
| **FAIL** | **8** | **$476M** | **28.1%** |

**The 28.1% TVL at risk under extreme stress is the headline number.** The eight failing markets cluster on:

1. **Pendle principal tokens.** Two of the three PT markets fail. Cause: low secondary-market liquidity amplified by the 25% drawdown.
2. **Leveraged liquid staking at high liquidation thresholds.** wstETH/WETH (LLTV 96.5%) and weETH/WETH (LLTV 94.5%) fail. The same pair listed at LLTV 86% passes. The leverage tier matters.
3. **Exotic synthetic stablecoins.** msY/USDC and sUSDat/AUSD fail despite being classified as stablecoin-synthetic. Both have very low Total Value Locked (under $20M) and few active positions; we caveat these as plausible artefacts of small-sample variance in the Beta-scaled position distribution.

---

## Honest limitations

We treat known failures as data:

- **3 corner cases require investigation.** stcUSD/USDT passes the extreme test with zero liquidations, possibly because the synthetic price feed is yield-adjusted and partially insulated from the drawdown injection. LBTC/PYUSD passes with three liquidations and zero bad debt, clean closure rather than insolvency. msY/USDC passes nominal-strong but fails extreme, likely small-sample variance in the position distribution.
- **Position-level reconstruction is approximate.** We use a parametric Beta with mean 0.65 × LLTV. A production deployment should reconstruct actual position-level LTVs from collateral and borrow events.
- **Maximal-extractable-value and liquidator-competition effects are not modelled.** Liquidations are atomic at modelled DEX prices; in reality, gas-price competition can leave some liquidations unprofitable.
- **The continuous LCR criterion returns Pr(LCR < 1) = 0% across all 26 markets.** This is plausibly a positive signal: under BCBS-aligned stress with healthy overcollateralisation, no Morpho Blue market we analysed approaches the LCR threshold of 1. But it could also signal that the LCR criterion as parameterised is insufficiently sensitive to extreme tail risks; the extreme stress test is the discriminating signal.

---

## Reproducibility

```bash
git clone https://github.com/YungBandulf/stressMorphoBlue
cd stressMorphoBlue && uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
PYTHONPATH=src pytest tests/        # 145 tests, ~2 minutes
PYTHONPATH=src python scripts/enrich_forward_looking.py --evaluate --extreme
```

The Dune dashboard with live TVL, top markets, and liquidation flows is at:
https://dune.com/bandulf/morpho-blue-liquidity-stress

---

## What this work is not

Not investment advice. Not a security audit. Not a recommendation to deposit on or borrow from any Morpho Blue lending market. The author has no affiliation with Morpho Labs, MetaMorpho vault curators, or any protocol mentioned, beyond public usage.

The contribution is methodological: a reproducible, falsifiable risk framework grounded in regulatory practice and applied to live data, with explicit limitations.

---

*Source: github.com/YungBandulf/stressMorphoBlue*
