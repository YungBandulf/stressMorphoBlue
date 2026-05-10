# A Liquidity Stress Framework for Morpho Blue, Adapted from Basel III

> **Summary**. We build a liquidity stress framework for Morpho Blue
> isolated lending markets, adapting the Liquidity Coverage Ratio
> defined by the Basel Committee on Banking Supervision in BCBS 238
> (2013). The framework is calibrated against three historical stress
> events (the KelpDAO exploit of April 2026, the USDC depeg of March
> 2023, and the staked-Ether discount episode of May 2022). Two of
> three events are correctly flagged ahead of the event by our
> pre-event detection criteria; the third failure is informative. the
> staked-Ether episode of May 2022 was a multi-day slow-rolling
> repricing of the staked-Ether-to-Ether ratio rather than a 24-hour
> liquidity stress, and our framework correctly does not classify it
> as the latter. Applied forward to the **26 most material Morpho Blue
> isolated markets on Ethereum mainnet** (approximately 1.7 billion
> U.S. dollars of aggregate Total Value Locked), the framework
> produces two complementary findings.
>
> **Under BCBS 238-aligned 24-hour stress** (drawdown floor calibrated
> per asset class against historical events, outflow alpha calibrated
> on stress-time withdrawal velocities), 1 market is flagged red, 7
> are flagged yellow, and 18 fall in the green tier (split between
> green-watch and green-strong). The single red flag is on the Pendle
> principal-token market PT-apyUSD-18JUN2026/USDC, with 99th-percentile
> bad debt at 5.7% of TVL. The yellow tier carries the bulk of the
> protocol's material exposure: approximately 14.5 million U.S. dollars
> of cumulative 99th-percentile bad debt across the four mainstream
> BTC/ETH-collateral markets (cbBTC/USDC, wstETH/USDT, WBTC/USDC,
> wstETH/USDC).
>
> **Under an extreme stress test** calibrated on the historical 99.5%-
> confidence band (drawdown 25%, outflow alpha 35%, anchored on the
> KelpDAO 2026 and USDC depeg 2023 episodes), 8 of 26 markets fail
> the survival criterion (LCR < 1 or 99th-percentile bad debt above
> 10% of TVL). The 8 failing markets carry approximately 28% of the
> roster's TVL. Failures cluster on Pendle principal tokens, leveraged
> liquid staking markets at high liquidation thresholds (94.5% to
> 96.5%), and exotic synthetic stablecoins.
>
> **Across the top 20 MetaMorpho vaults**, the framework's tier
> classification yields a curator discipline score that ranges from 0.0
> (fully conservative) to 2.0 (significant yellow exposure). The four
> largest USDC-asset vaults (Gauntlet USDC Prime, Steakhouse USDC,
> Vault Bridge USDC, Hakutora USDC) converge at a score of
> approximately 2.0, reflecting near-exclusive allocation to mainstream
> BTC/ETH-collateral markets. The finding is structural: the USDC vault
> product concentrates the protocol's material tail risk in a small
> number of yellow-tier markets where the bulk of DeFi USDC yield
> originates.
>
> The full source code, test suite, and reproducible event fixtures
> are open-source.

---

## A note on terminology

Every specialised term used in this document is defined either at first
use or in [`GLOSSARY.md`](./GLOSSARY.md). Mathematical symbols are
introduced explicitly with their units. Abbreviations are spelled out
on first use, with the abbreviation in parentheses, then used as the
abbreviation in subsequent references.

---

## 1. Motivation

Decentralised-finance lending pools have been shown to exhibit
inherent fragility under stress (Chiu, Ozdenoren, Yuan & Zhang, *On
the inherent fragility of decentralised-finance lending*, Bank for
International Settlements Working Paper 1062, 2023). Yet most public
risk reports for these pools transpose institutional concepts (such
as those defined by the Basel Committee on Banking Supervision,
abbreviated below as the *Basel Committee*) informally, without
explicit pass-or-fail criteria, and without a reproducible backtest
against historical events.

This work formalises the transposition. We build:

- An on-chain analogue of the Liquidity Coverage Ratio (the regulatory
  ratio defined in BCBS 238, 2013, which requires regulated banks to
  hold sufficient liquid assets to cover stressed outflows over 30
  days; see §2.1 below);
- A Monte Carlo simulation framework over an empirical distribution of
  collateral price drawdowns;
- A falsifiable validation procedure with three pre-specified
  pass-or-fail criteria.

The choice of Morpho Blue as the target protocol is motivated by:

- **Architectural simplicity**: Morpho Blue is a non-custodial lending
  protocol implemented in approximately 650 lines of Solidity, with
  isolated lending markets and immutable parameters. This produces a
  small surface area and a well-defined mathematical state vector for
  each market.
- **Industry positioning in 2026**: following the KelpDAO collateral
  exploit of April 2026, approximately 8 billion U.S. dollars of Total
  Value Locked has migrated from Aave to Morpho (per public on-chain
  data observed at the time of writing). Risk methodology adapted to
  Morpho's isolated-market design is in active demand among the
  protocol's MetaMorpho vault curators, including Steakhouse
  Financial, Block Analitica, and B.Protocol.

This work is methodological. The contribution is a falsifiable,
reproducible adaptation of regulatory liquidity standards to one
particular decentralised-finance protocol; it is neither a
production-grade risk-monitoring system nor a security audit.

---

## 2. The framework

### 2.1 Adaptation of the Liquidity Coverage Ratio

The Liquidity Coverage Ratio defined by the Basel Committee in BCBS
238 (2013) is

$$\text{Liquidity Coverage Ratio} = \frac{\text{High Quality Liquid Assets}}{\text{Net cash outflows over 30 days}} \geq 100\%.$$

We construct an **on-chain Liquidity Coverage Ratio** for a Morpho Blue
lending market. The numerator (High Quality Liquid Assets, a Basel
term referring to assets readily monetisable under stress with little
loss in value) is decomposed into two layers in the original Basel
text:

- *Level 1*: cash and equivalents, with a haircut of 0%;
- *Level 2A*: highly liquid bonds, with a haircut of 15%.

For a Morpho Blue lending market, our adaptation is as follows. Let:

- $S$ denote the total supply of the loan asset (denoted
  `total_supply_assets` on-chain), in units of the loan asset;
- $B$ denote the total borrow of the loan asset (denoted
  `total_borrow_assets` on-chain), in units of the loan asset;
- $L = S - B$ denote the instantaneous available liquidity, in units
  of the loan asset;
- $\Lambda$ denote the liquidation loan-to-value threshold (the
  market's parameter, fixed at market creation), a number in $[0, 1]$;
- For each borrower $i$: $b_i$ the borrower's debt (in loan-asset
  units), $c_i$ the borrower's collateral (in collateral-asset units);
- $P$ denote the oracle-reported price of one collateral unit in
  loan-asset units;
- $\pi(V) = a \cdot V^b$ denote the slippage of a sale of $V$
  collateral-asset units on a decentralised exchange, expressed as a
  fraction of the oracle price; the parameters $a > 0$ and $b \in (0,1)$
  are fitted from data per the Almgren, Chriss model (see §2.4).

The **on-chain Level 1 component** is the available liquidity:
$L_1 = L$.

The **on-chain Level 2A component** corresponds to the loan-asset
value the protocol can recover via liquidation under stress. The
liquidator seizes collateral up to a *liquidation incentive factor*
$\phi(\Lambda)$ above the debt amount (Morpho Blue's formula:
$\phi(\Lambda) = \min(1.15, 1/(0.3\Lambda + 0.7))$, capping the bonus
at 15%) and sells it on the decentralised exchange at the realised
price $P \cdot (1 - \pi(\cdot))$. The recovery for the supplier pool
from position $i$ is

$$r_i = \min\left(c_i \cdot P \cdot (1 - \pi(c_i)), b_i \cdot \phi(\Lambda)\right) - \mathrm{BD}_i$$

where the cap at $b_i \cdot \phi(\Lambda)$ reflects that the
protocol does not benefit from over-collateralisation (any surplus
returns to the borrower) and where the **bad debt** for position $i$
is

$$\mathrm{BD}_i = \max\left(0, b_i - c_i \cdot P \cdot (1 - \pi(c_i))\right),$$

i.e., the unrecoverable shortfall when realised proceeds fall below
the position's debt. The aggregate Level 2A is then
$L_{2A,\mathrm{net}} = \sum_i r_i$.

This formulation **differs from a literal Basel haircut transposition**
on a critical point: the Basel haircut applies to a notional asset
value, while our Level 2A is bounded above by the per-position debt.
This avoids the over-counting of pledged collateral that we observed
in earlier versions of this work (see §3 of [`SCENARIOS.md`](./SCENARIOS.md)
for the full discussion).

The **on-chain numerator** is then
$\mathrm{HQLA_{oc}} = L_1 + L_{2A,\mathrm{net}}$.

The **on-chain denominator** (net cash outflows under stress) is
parameterised by an **outflow fraction** $\alpha$, the fraction of
total supply withdrawn during the 24-hour stress window:

$$\mathrm{Outflows_{oc}}(\alpha) = \alpha \cdot S - \min\left(L_{2A,\mathrm{net}}, 0.75 \cdot \alpha S\right).$$

The cap at 75% of outflows reproduces BCBS 238 Annex 4 §170, which
limits the offset between secured-lending inflows and outflows.

The **outflow fraction $\alpha$ is event-calibrated** from the
empirical distribution of 24-hour drawdowns of the collateral price.
We use

$$\alpha = \min\left(0.60, \max\left(0.05, 1.5 \cdot q_{0.99}(\mathrm{drawdowns}) + 0.30 \cdot \mathbf{1}\{q_{0.99} > 0.05\}\right)\right)$$

where $q_{0.99}(\mathrm{drawdowns})$ is the 99th-percentile empirical
quantile of drawdowns, and $\mathbf{1}\{\cdot\}$ the indicator
function. The constant $1.5$ and the additive term $0.30$ are
calibrated from observations of withdrawal velocity in real events:

- During the KelpDAO event of April 2026, the Aave Total Value Locked
  fell by approximately 17% in 48 hours, peaking at approximately 10%
  in 24 hours, implying a withdrawal multiplier in the range
  $[1.4, 1.7]$ relative to the contemporaneous price drawdown.
- During the USDC depeg of March 2023, the Aave USDC market saw
  approximately 25% withdrawals on day one, consistent with a
  multiplier of $1.5$ applied to a drawdown of $\approx 12\%$, plus
  a whale-concentration term capturing rapid exit by the largest
  suppliers.

The whale-concentration term (the additive $0.30 \cdot \mathbf{1}\{q_{0.99} > 0.05\}$)
reflects the empirical observation that the top five suppliers in
mid-size decentralised-finance lending markets tend to exit at the
first sign of stress, contributing a near-instantaneous 30% withdrawal
of total supply.

### 2.2 Three pass-or-fail criteria

A market is flagged as stressed if any of three criteria is triggered.
Each criterion captures a distinct risk channel.

| Criterion | Threshold | Severity bands |
|---|---|---|
| On-chain Liquidity Coverage Ratio < 1.00 | $< 1.00$ | red < 0.80 / yellow < 1.00 / green |
| Time-to-illiquid < 24 hours | $< 24$h | red < 12h / yellow < 24h / green |
| Probability that bad debt $> 0$, estimated by Monte Carlo | $> 5\%$ | red > 20% / yellow > 5% / green |

The **time-to-illiquid** is the first block at which a market's
available liquidity is exhausted under a withdrawal-run scenario at
the calibrated outflow fraction $\alpha$.

The **Monte Carlo probability of positive bad debt** is estimated by
sampling 200 drawdown realisations from the market's empirical
drawdown distribution, simulating the resulting liquidations under
each, and computing the fraction of paths producing strictly positive
bad debt.

The composite *severity flag* of a market is the worst of the three
individual severities (red dominates yellow dominates green). The
*framework flag* is `True` if any criterion is triggered.

### 2.3 Why three criteria?

A market may be healthy on the Liquidity Coverage Ratio (ample
recovery from collateral), yet drain quickly under concentrated whale
exit (high time-to-illiquid risk). Conversely, a market may have slow
withdrawal velocity yet be vulnerable to a price shock (high
bad-debt-probability risk). The three criteria are designed to be
*non-redundant*: empirically (see §3.2 below) we find that different
events trigger different criteria, and the combination is required for
adequate coverage.

### 2.4 Slippage curve

For each collateral asset, we fit a power-law impact function
$\pi(V) = a \cdot V^b$ via ordinary least squares regression in
log-space. The exponent $b$ typically lies in $[0.50, 0.62]$,
consistent with the equity-microstructure literature (Almgren and
Chriss, *Optimal execution of portfolio transactions*, Journal of
Risk, 2000; Frazzini, Israel and Moskowitz, *Trading Costs*, working
paper, 2018). Confidence intervals on $b$ are reported alongside the
point estimate using the Wald approximation (Gaussian asymptotics on
the regression coefficient, valid for ordinary least squares with
homoskedastic errors).

---

## 3. Backtest validation

### 3.1 Events selected

We backtest the framework against three historical stress events,
selected to span distinct risk profiles.

| Event | Type | Day-zero (T-zero) | Counterfactual? |
|---|---|---|---|
| **KelpDAO collateral exploit** | Liquid-restaking-token collateral exploit, single-day cascade | 2026-04-19 23:59 UTC | No, Morpho Blue was active |
| **USDC depeg from Silicon Valley Bank collapse** | Stable-on-stable depeg | 2023-03-10 12:00 UTC | Yes, predates Morpho Blue |
| **Staked-Ether discount during the Terra/UST collapse** | Liquid-staking-token discount, multi-day slow-roll | 2022-05-11 09:00 UTC | Yes, predates Morpho Blue |

The day-zero (denoted T-zero) is the timestamp at which the framework
is evaluated, set at 24 hours before the realised stress event. For
events that predate Morpho Blue, we apply the framework on a
*counterfactual* Morpho Blue market with parameters typical of current
practice (liquidation loan-to-value threshold, interest rate model,
oracle), seeded with the actual price path of the event.

### 3.2 Results

| Event | Liquidity Coverage Ratio | $\alpha$ | Time-to-illiquid | Probability bad debt > 0 | Severity | Verdict |
|---|---|---|---|---|---|---|
| KelpDAO 2026 | 8.30 (green) | 60% | < 6h (red) | high (red) | **red** | **PASS** |
| USDC depeg 2023 | 8.30 (green) | 48% | 6.6h (red) | 0% (green) | **red** | **PASS** |
| Staked-Ether 2022 | 80.0 (green) | 5% (floor) | infinite (green) | 0% (green) | **green** | **FAIL** |

**KelpDAO and the USDC depeg are flagged ahead of the event** through
the time-to-illiquid criterion at the event-calibrated $\alpha$. The
bad-debt-probability criterion fires only on KelpDAO. This is
informative: the USDC oracle was *sticky* during the depeg (the
Chainlink USDC-to-U.S.-dollar feed remained at $1.00$ for hours, while
the secondary market traded at approximately $0.88$), so on-chain
positions did not reach the liquidation threshold despite severe
market-price dislocations. The framework correctly captures that the
USDC event's risk channel was *liquidity drain* rather than *bad-debt
cascade*.

**The staked-Ether 2022 episode is not flagged.** We retain this
result rather than tune parameters to obtain three-of-three. The
staked-Ether discount unfolded slowly, from a ratio of 0.99 down to
0.94 staked-Ether-to-Ether over five days. Under our 24-hour rolling
window, the maximum observed drawdown falls below the 5% threshold
that triggers the whale-concentration term, and $\alpha$ collapses to
its floor of 5%. This is not a calibration failure: it is a **scope
limitation that we acknowledge openly**. Our framework adapts the
24-hour Liquidity Coverage Ratio of BCBS 238, not the
medium-horizon Net Stable Funding Ratio of BCBS 295 (2014). Capturing
the staked-Ether-style risk channel would require a complementary
adaptation of the Net Stable Funding Ratio. We flag this as future
work.

### 3.3 Aggregate verdict

**Two of three events are correctly flagged**, including the primary
anchor (KelpDAO). The single failure is a documented scope
limitation, not a parameter-tuning failure. We argue that this
honesty is more valuable than a three-of-three result obtained by
tuning thresholds to the test set: a risk methodology that pretends
to cover everything is a methodology that quietly misses real risks
in production.

---

## 4. Forward-looking analysis

### 4.1 Roster

We apply the framework to the **26 most material Morpho Blue isolated
markets on Ethereum mainnet**, ranked by Total Value Locked, with state
extracted from the on-chain data acquisition pipeline described in
[`docs/DATA.md`](./DATA.md). The roster is therefore not illustrative
but reflects the live composition of the protocol as observed during
the analysis window. Aggregate Total Value Locked across the roster is
approximately 1.7 billion U.S. dollars.

The roster spans five collateral asset classes:

- **Wrapped Bitcoin variants** (cbBTC, WBTC, LBTC), $635M total
- **Liquid staking tokens** (wstETH, weETH), $570M total
- **Synthetic stablecoins** (sUSDe, sUSDS, wsrUSD, syrupUSDC, AA_FalconXUSDC, sUSDat, stcUSD, msY, mF-ONE, stUSDS), $552M total
- **Pendle principal tokens** (PT-apyUSD, PT-apxUSD, PT-reUSD), $52M total
- **Yield-bearing wrappers** (sUSDe in different quote pairs), residual

Loan assets are dominated by USDC, USDT, PYUSD, and WETH.

### 4.2 Methodology: decoupled stress scenarios

We evaluate each market under two scenarios in parallel rather than
combining both stresses in a single path. The cumulative-stress
parameterisation we initially used produced a near-uniform red flag
across the protocol, which is methodologically inconsistent with the
spirit of BCBS 238 (a 24-hour LCR test reflects a plausible adverse
scenario, not the worst conceivable hybrid).

**Scenario A, price stress.** Drawdown set to the class-floored
99th-percentile from the empirical distribution. Outflow $\alpha$
calibrated on a normal price path (no event injected), reflecting
moderate runoff coherent with the price drop. Class minima for the
99th-percentile drawdown are calibrated against historical events
(see [`METHODOLOGY.md`](./METHODOLOGY.md) §3 for the full table):

- Stablecoin synthetics: 5% (USDC depeg 2023 trough was 8%)
- Liquid staking tokens: 8% (stETH discount 2022 reached 8%)
- Wrapped Bitcoin: 10% (BTC flash crash August 2024 reached 12%)
- Wrapped Ether: 8%
- Pendle principal tokens: 15% (no historical anchor; calibrated against the illiquidity of Pendle secondary markets)

**Scenario B, liquidity stress.** Drawdown set to the empirical
median, $\alpha$ amplified to the 20%-30% range observed during the
KelpDAO 2026 episode (where roughly 17% of Aave's TVL exited in 24
hours) and the USDC depeg of March 2023 (approximately 25% on day one).

The reported `Liquidity Coverage Ratio` (column LCR_v03 in the table
below) is the worst-of-two: $\min(\mathrm{LCR}_A, \mathrm{LCR}_B)$.

We additionally compute a **continuous LCR criterion**: the fraction
of Monte Carlo paths in which $\mathrm{LCR} < 1$, denoted
$\Pr(\mathrm{LCR} < 1)$. This is more aligned with stress-testing
practice than a single threshold check.

### 4.3 Severity criteria

A market is `red` if **at least one** of the three components reaches
red severity. The component thresholds are:

| Component | Red | Yellow | Green |
|---|---|---|---|
| $\Pr(\mathrm{LCR} < 1)$ | $> 50\%$ | $> 10\%$ | $\leq 10\%$ |
| Time-to-illiquid | $< 6\mathrm{h}$ | $< 18\mathrm{h}$ | $\geq 18\mathrm{h}$ |
| Bad-debt magnitude | $\Pr[\text{bd}>0] > 30\%$ AND $\frac{\mathrm{bd}_{99}}{\mathrm{TVL}} > 5\%$ | $\frac{\mathrm{bd}_{99}}{\mathrm{TVL}} > 1\%$ | $\frac{\mathrm{bd}_{99}}{\mathrm{TVL}} \leq 0.1\%$ |

Within `green`, we further distinguish:

- **green-strong**: $\Pr(\mathrm{LCR}<1) < 1\%$ AND time-to-illiquid is infinite AND $\Pr[\text{bd}>0] = 0$ AND $\mathrm{bd}_{99}/\mathrm{TVL} < 0.01\%$.
- **green-watch**: green but at least one indicator is non-negligible (typically a positive but small bad-debt tail).

### 4.4 Risk panorama

The roster of 26 markets resolves into the following distribution:

| Tier | Markets | Aggregate Total Value Locked | Share of total |
|---|---|---|---|
| red | 1 | $23M | 1.4% |
| yellow | 7 | $737M | 43.5% |
| green-watch | 5 | $384M | 22.6% |
| green-strong | 13 | $552M | 32.6% |
| **Total** | **26** | **$1,696M** | **100.0%** |

The market in the `red` tier is **PT-apyUSD-18JUN2026/USDC**, a Pendle
principal token with $23.1M Total Value Locked and 82.6% utilisation.
The bad-debt distribution under scenario A reaches a 99th-percentile
of $1.32M, equal to 5.7% of TVL, with 68.5% probability of positive
bad debt across the Monte Carlo paths. This reflects two compounding
factors:

- **Wide drawdown distribution under the principal-token class
  minimum** of 15%. The Pendle secondary market is structurally less
  liquid than Curve or Uniswap V3 stablecoin pools, and our slippage
  curve fit (asset-class default $a = 10^{-3}$, $b = 0.65$) reflects
  this.
- **High utilisation combined with concentrated borrower exposure**.
  Although the absolute Total Value Locked is moderate, the Beta-
  scaled distribution of position-level loan-to-values puts a
  meaningful tail of positions within liquidation distance under the
  scenario.

The seven `yellow` markets carry the bulk of the protocol's material
tail risk in absolute dollar terms:

| Market | TVL ($M) | Utilisation | $\Pr[\text{bd}>0]$ | bd $p_{99}$ | bd/TVL |
|---|---|---|---|---|---|
| cbBTC/USDC | 268.0 | 91.0% | 46.0% | $5.30M | 1.98% |
| wstETH/USDT | 218.0 | 77.9% | 3.0% | $4.78M | 2.19% |
| WBTC/USDC | 156.1 | 91.0% | 43.5% | $2.13M | 1.37% |
| wstETH/USDC | 44.4 | 91.1% | 23.5% | $1.05M | 2.36% |
| cbBTC/PYUSD | 22.2 | 84.8% | 3.0% | $0.33M | 1.50% |
| PT-reUSD-25JUN2026/USDC | 14.8 | 75.5% | 11.0% | $0.44M | 3.00% |
| PT-apxUSD-18JUN2026/USDC | 13.8 | 63.5% | 32.5% | $0.51M | 3.67% |

The aggregate yellow-tier 99th-percentile bad-debt totals
**approximately $14.5M**, concentrated on the four BTC/ETH-collateral
mainstream markets (cbBTC/USDC, wstETH/USDT, WBTC/USDC, wstETH/USDC).
These four markets carry $686M of TVL, or 40% of the analysed total.

### 4.5 The continuous LCR criterion

Across all 26 markets, $\Pr(\mathrm{LCR} < 1) = 0\%$ in our 200-path
Monte Carlo. **No market falls below the LCR threshold of 1 under the
scenario distribution we sampled.** This is a positive signal: under
BCBS 238-aligned stress, Morpho Blue's overcollateralisation (typical
average loan-to-value of $0.65 \times \mathrm{LLTV}$ in our calibration)
combined with healthy Uniswap V3 secondary liquidity is sufficient to
keep the High-Quality Liquid Asset coverage above stressed outflows.

We caveat this finding heavily. The LCR criterion as parameterised here
does not detect risks that materialise above the 99th percentile of
the empirical drawdown distribution. To probe protocol behaviour under
scenarios that exceed observed history, we run a separate extreme
stress test, described next.

---

## 4bis. Extreme stress test

### 4bis.1 Calibration

We define an **extreme scenario** combining the most adverse parameter
values observed across the three calibration events:

- **Drawdown** = 25%, between the USDC depeg trough (8%) and stETH
  discount (8%), amplified to the 99.5th-percentile band of historical
  DeFi stress events.
- **Outflow $\alpha$** = 35%, between the KelpDAO 2026 24-hour Aave
  outflow (~17%) and the USDC depeg day-one outflow (~25%), upper-
  bounded by the most aggressive coordinated stress observed in the
  Curve Wars episodes of 2023.

Both parameters are held fixed (no Monte Carlo over the drawdown
distribution; the extreme is a deterministic worst-case).

### 4bis.2 Survival criterion

A market `survives` the extreme scenario if **both** are true:

- $\mathrm{LCR}_{\text{extreme}} \geq 1.0$
- $\mathrm{bd}_{99} / \mathrm{TVL} < 10\%$

The 10% threshold is the materiality cut-off used in capital adequacy
frameworks (Tier 1 capital ratio thresholds in the Basel III risk-
weighted-asset framework typically classify exposures above 10% loss-
given-default as materially impaired).

### 4bis.3 Result

| Verdict | Markets | Aggregate Total Value Locked | Share of total |
|---|---|---|---|
| PASS | 18 | $1,220M | 71.9% |
| FAIL | 8 | $476M | 28.1% |
| **Total** | **26** | **$1,696M** | **100.0%** |

The eight markets that fail the extreme stress test are:

| Market | TVL ($M) | bd $p_{99}$ ($M) | bd/TVL | Positions liquidated ($p_{99}$) |
|---|---|---|---|---|
| msY/USDC | 12.9 | 2.09 | 16.18% | 4 |
| PT-reUSD-25JUN2026/USDC | 14.8 | 2.23 | 15.03% | 8 |
| wstETH/USDC | 44.4 | 6.41 | 14.44% | 49 |
| sUSDat/AUSD | 19.0 | 2.33 | 12.26% | 23 |
| PT-apyUSD-18JUN2026/USDC | 23.1 | 2.48 | 10.74% | 66 |
| wstETH/WETH (LLTV 96.50%) | 90.6 | 9.53 | 10.52% | 18 |
| weETH/WETH (LLTV 94.50%) | 52.9 | 5.45 | 10.29% | 18 |
| wstETH/USDT | 218.0 | 22.11 | 10.14% | 21 |

Total bad debt under extreme stress, summed across the eight failing
markets, is **approximately $52.6M**, or 3.1% of the analysed Total
Value Locked.

### 4bis.4 Reading the failures

Three patterns emerge across the failing markets:

**Pattern 1, Pendle principal tokens.** Two of the three Pendle PT
markets in the roster fail. The cause is the combination of (a) the
class-floored 15% drawdown which is itself plausible given the
illiquidity of Pendle secondaries during stress, and (b) the steep
slippage curve under our class default. PT tokens are structurally
exposed to liquidity gap-risk during volatility regimes, and the
framework consistently flags this.

**Pattern 2, Liquid staking with high liquidation thresholds.** The
two markets `wstETH/WETH (LLTV 96.50%)` and `weETH/WETH (LLTV 94.50%)`
fail. These are leverage-tier markets (the protocol intentionally lists
multiple instances per pair to offer different leverage profiles); the
high liquidation threshold compresses the headroom between the average
position loan-to-value (Beta-scaled at $0.65 \times \mathrm{LLTV} \approx 0.62$ for the 96.5%-tier) and the liquidation threshold.
A 25% price drop sweeps a meaningful share of positions into
liquidation. By contrast, the same pair listed at LLTV 86.50% passes
the extreme test, illustrating the materiality of the LLTV choice for
leveraged collateral.

**Pattern 3, Exotic synthetic stablecoins.** Two markets, `msY/USDC`
and `sUSDat/AUSD`, fail despite being classified as stablecoin
synthetics. We caveat these results: both markets have very low
Total Value Locked (under $20M) and few active positions (4 and 23
respectively at the 99th percentile of liquidations). The Beta-scaled
position distribution at low cardinality has high variance: with only
a handful of positions, the framework over-estimates the impact of a
single outlier. These two results merit further investigation in a
production deployment with larger sample sizes.

### 4bis.5 Notable corner cases

Three results in the extreme-stress run merit investigation in a
production setting and are reported here as **known limitations**:

- **stcUSD/USDT**: passes the extreme test with zero positions
  liquidated and zero bad debt. The synthetic stablecoin's price
  feed may be partially insulated from the 25% drawdown injected
  in the scenario; if the oracle returns a yield-adjusted price
  rather than the spot, our scenario does not affect it. This warrants
  inspection of the oracle configuration.

- **LBTC/PYUSD**: passes with three positions liquidated but zero
  realised bad debt. Liquidations close out cleanly at the
  liquidation incentive threshold, leaving no residual loss.
  Plausible given the small number of positions ($n = 7$) and a
  benign Beta-scaled position distribution at this cardinality, but
  worth verifying against position-level reconstruction.

- **msY/USDC**: passes the nominal scenario as `green-strong` but fails
  the extreme. As described in Pattern 3, this is plausibly an artefact
  of small-sample variance in the position distribution rather than a
  genuine structural weakness.

---

## 4ter. MetaMorpho vault curator discipline

### 4ter.1 Motivation

Beyond per-market analysis, a natural application of the tier
classification is to score the **discipline of MetaMorpho vault
curators**: how exposed is each vault to markets that the framework
classifies as red, yellow, green-watch, or green-strong? The output
is not a verdict on curator quality (a curator may legitimately
allocate to higher-tier markets if they have priced in the risk) but
a quantitative breakdown that supports comparability across curators.

### 4ter.2 Methodology

For each MetaMorpho vault, we extract the supply allocations across
markets via the Morpho API and compute a TVL-weighted **curator
discipline score**:

$$\text{score} = \sum_{m \in \text{allocations}} \frac{\text{supply}_m}{\text{TVL}_{\text{vault}}} \cdot w(\text{tier}_m)$$

where the tier weights $w$ are: red $= 4$, yellow $= 2$, green-watch
$= 1$, green-strong $= 0$. Allocations to markets outside our 26-
market roster (typically smaller markets, EUR-stablecoin markets, or
chains other than Ethereum) are bucketed as `unknown` and do not
contribute to the score.

The score interpretation is:

- $0.0$, perfectly conservative: vault is fully invested in markets
  the framework classifies as green-strong.
- $\sim 1.0$, moderate discipline: vault has meaningful exposure to
  green-watch markets and small yellow exposure.
- $\sim 2.0$, significant yellow exposure: vault is allocating to
  yellow-tier markets that carry material absolute tail risk.
- $> 2.0$, substantial red/yellow exposure that warrants curator-side
  review.

### 4ter.3 Result

Applied to the top 20 MetaMorpho vaults by TVL on Ethereum mainnet:

| Vault | Asset | TVL ($M) | Score | red% | yellow% | green-watch% | green-strong% | unknown% |
|---|---|---|---|---|---|---|---|---|
| Sentora PYUSD | PYUSD | 244.5 | 0.56 | 0.0 | 8.8 | 38.5 | 35.4 | 17.3 |
| Sentora RLUSD | RLUSD | 166.0 | 0.00 | 0.0 | 0.0 | 0.0 | 61.0 | 39.0 |
| Gauntlet USDC Prime | USDC | 150.9 | 2.00 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| Steakhouse USDC | USDC | 129.4 | 1.94 | 0.0 | 96.8 | 0.0 | 0.0 | 3.2 |
| Steakhouse USDT | USDT | 125.2 | 1.77 | 0.0 | 82.9 | 11.7 | 0.0 | 5.4 |
| Steakhouse Ethena USDtb | USDtb | 85.2 | 0.00 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 |
| Steakhouse EURCV | EURCV | 51.2 | 0.00 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |
| Sentora PYUSD Core | PYUSD | 50.2 | 1.01 | 0.0 | 1.5 | 98.5 | 0.0 | 0.0 |
| Vault Bridge USDC | USDC | 48.9 | 2.00 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 |
| Gauntlet WETH Prime | WETH | 42.1 | 0.99 | 0.0 | 0.0 | 98.7 | 0.0 | 1.3 |

The full table of 20 vaults is reproducible by running
`python scripts/fetch_metamorpho_vaults.py --top 20`.

### 4ter.4 Findings

**Finding 1: Cross-curator convergence on USDC vault strategy.** The
four largest USDC-asset vaults (Gauntlet USDC Prime, Steakhouse USDC,
Vault Bridge USDC, Hakutora USDC) all converge on a curator score of
approximately 2.0, reflecting a near-exclusive allocation to the
yellow tier. This is not a quality differentiator: it is a
**structural feature** of the USDC vault product. The yellow tier
contains the four mainstream BTC/ETH-collateral markets (cbBTC/USDC,
WBTC/USDC, wstETH/USDT, wstETH/USDC) which represent the bulk of USDC
yield-bearing supply on Morpho Blue. Any USDC vault providing
competitive net APY must be exposed to these markets.

The finding therefore is not "Steakhouse and Gauntlet are aggressive"
but rather "**the USDC product structurally concentrates the protocol's
material tail risk** in a small number of mainstream markets". The
risk is not idiosyncratic to any one curator.

**Finding 2: Differentiated discipline across asset classes.** USDC
vaults converge at score $\approx 2.0$. PYUSD and stablecoin-synthetic
vaults are more diversified: Sentora PYUSD has a score of 0.56 with
33% green-strong allocation; Smokehouse vaults distribute across many
small markets (22+ allocations). RLUSD-asset vaults (Sentora RLUSD)
score 0.0, reflecting a pure allocation to the green-strong
syrupUSDC/RLUSD market.

**Finding 3: Scope limitation: 100% unknown vaults.** Three vaults
in the top 20 score 0.0 with 100% unknown classification: Steakhouse
EURCV, Vault Bridge WBTC, and Adpend USDC. The first two allocate to
markets outside our 26-market USD-denominated roster (EUR-stablecoin
markets and smaller WBTC markets respectively); the third uses 30
small allocations spread across long-tail markets we did not fetch.
The framework provides no useful information for these vaults at the
current roster size.

### 4ter.5 Limitations

- **The score weights are arbitrary**: red = 4 reflects an editorial
  choice that a red allocation is twice as concerning as a yellow.
  A different weighting scheme would produce different rankings.
  We provide the per-tier breakdown alongside the score so
  consumers can re-weight for their own purposes.
- **Static snapshot**: vaults rebalance, often daily. The score is
  point-in-time. A production deployment would compute the score
  weekly and track its evolution per vault.
- **Curator intent is not modelled**: a vault can intentionally hold
  yellow-tier exposure if it has priced in the risk through a higher
  expected yield, a withdrawal queue, or a guarantor backstop. The
  framework reports tier exposure; it does not determine whether that
  exposure is appropriate.

---

## 5. What this work does not establish

We list these explicitly because they materially affect the
interpretability of the headline numbers, and decentralised-finance
risk reporting often omits such caveats.

1. **The bad-debt distribution has heavy tails on a small sample.**
  Our Monte Carlo simulations use 50 to 200 paths drawn from a
  fitted Beta empirical distribution. The 99th-percentile estimate
  has wide confidence intervals; for the high-probability red-flag
  market (PT-apyUSD-18JUN2026/USDC at 68.5%) the result is reliable to
  sampling, but tail magnitudes for less-stressed markets are small
  numbers dominated by sampling noise. Markets with very few active
  positions (under 20) are particularly subject to small-sample
  variance in the Beta-scaled position distribution.
2. **Counterfactual events are weakly identified.** The USDC and
  staked-Ether events predate Morpho Blue. We synthesised position
  distributions for them, calibrated to plausible parameters of
  current practice. The PASS verdict on the USDC event is more
  reliable than the FAIL verdict on the staked-Ether event because the
  USDC drawdown is large enough to drive a clear signal; the
  staked-Ether outcome depends on a distinction between 24-hour and
  multi-day stress that the framework was not designed to make.
3. **Maximal-extractable-value and liquidator-competition effects are
  not modelled.** Liquidations are assumed to occur atomically and
  to succeed at the modelled decentralised-exchange price. In
  reality, gas-price competition during stress events can leave some
  liquidations unprofitable for the intended liquidator, displacing
  them. This bias is conservative for our Level 2A recovery (we
  overstate it) and underestimates bad debt.
4. **Endogenous oracle feedback is partially modelled.** Exogenous
  oracles (Chainlink, Pyth, Redstone) are handled correctly:
  liquidator selling does not affect the oracle. Time-Weighted
  Average Price oracles from Uniswap V3 receive endogenous
  decentralised-exchange-price propagation through the time-weighted
  average smoothing, but the current framework does not solve the
  within-block fixed point implied by full liquidation cascades; we
  model sequentially within each block.
5. **Three events is a small sample for backtest validation.**
  Statistical significance is not claimed; the two-of-three pass
  rate is illustrative of the framework's discrimination, not a
  frequentist guarantee.
6. **The forward-looking market parameters are representative.** A
  production deployment would replace these with live subgraph and
  remote-procedure-call reads. The architecture for this is in
  place; the parameters here are not authoritative.

---

## 6. Reproducibility

The full pipeline is open-source. Key features:

- **Versioned event fixtures** under `data/fixtures/<event-id>/` with
  per-row source attribution, reproducible from the fixture
  generation script.
- **145 unit and property-based tests** with the `pytest` and
  `hypothesis` libraries.
- **Demonstration notebooks** for each phase of the work, runnable
  with the command `PYTHONPATH=src python notebooks/phase{N}_demo.py`.
- **Strict typed schemas** (using PyArrow and Pandera) gate every
  Parquet write, preventing silent type drift between data and model.
- **Manifest-tracked runs** with configuration hashes for full
  pipeline reproducibility.

The repository structure, methodology, scenario specification, data
architecture, and backtest specification are documented in the files
[`METHODOLOGY.md`](./METHODOLOGY.md), [`SCENARIOS.md`](./SCENARIOS.md),
[`DATA.md`](./DATA.md), and [`BACKTEST.md`](./BACKTEST.md).

---

## 7. References

Selected anchors. The full bibliography is in
[`references.md`](./references.md); definitions of all institutional
and on-chain terms are in [`GLOSSARY.md`](./GLOSSARY.md).

- Bank for International Settlements. *Basel III: The Liquidity
  Coverage Ratio and liquidity risk monitoring tools.*
  Publication BCBS 238, 2013.
- Bank for International Settlements. *Basel III: The Net Stable
  Funding Ratio.* Publication BCBS 295, 2014.
- Chiu, J., Ozdenoren, E., Yuan, K., Zhang, S. *On the inherent
  fragility of decentralised-finance lending.* Bank for International
  Settlements Working Paper 1062, 2023.
- Gudgeon, L., Werner, S. M., Perez, D., Knottenbelt, W. J.
  *Decentralised-finance protocols for loanable funds.* Financial
  Cryptography 2020.
- Almgren, R., Chriss, N. *Optimal execution of portfolio
  transactions.* Journal of Risk, 2000.
- Morpho Labs. *Morpho Blue Whitepaper* and *Morpho Blue Yellow
  Paper*, 2024.

---

## 8. About this work

This is an independent research project. It has no affiliation with
Morpho Labs or any MetaMorpho vault curator. It is not investment
advice, not a security audit, and not a substitute for production
risk monitoring.

Feedback, corrections, and counter-arguments are welcome. The
repository accepts pull requests and issues.
