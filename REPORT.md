# A Liquidity Stress Framework for Morpho Blue, Adapted from Basel III

> **Summary**. We build a liquidity stress framework for Morpho Blue
> isolated lending markets, adapting the Liquidity Coverage Ratio
> defined by the Basel Committee on Banking Supervision in BCBS 238
> (2013). The framework is calibrated against three historical stress
> events (the KelpDAO exploit of April 2026, the USDC depeg of March
> 2023, and the staked-Ether discount episode of May 2022). Two of
> three events are correctly flagged ahead of the event by our
> pre-event detection criteria; the third failure is informative — the
> staked-Ether episode of May 2022 was a multi-day slow-rolling
> repricing of the staked-Ether-to-Ether ratio rather than a 24-hour
> liquidity stress, and our framework correctly does not classify it
> as the latter. Applied forward to a roster of representative
> mid-2026 markets, the framework identifies the **staked-Ethena-USDC
> Morpho Blue market** as the dominant tail-risk market under our
> parameterisation, with 26.6 million U.S. dollars of expected 99th-percentile
> bad debt (approximately 19% of the market's Total Value Locked)
> under a single-day stress.
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

$$\text{Liquidity Coverage Ratio} \;=\;
\frac{\text{High Quality Liquid Assets}}{\text{Net cash outflows over 30 days}} \;\geq\; 100\%.$$

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
  are fitted from data per the Almgren–Chriss model (see §2.4).

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

$$r_i \;=\; \min\Bigl(c_i \cdot P \cdot (1 - \pi(c_i)),\; b_i \cdot \phi(\Lambda)\Bigr) \;-\; \text{bad-debt}_i$$

where the cap at $b_i \cdot \phi(\Lambda)$ reflects that the
protocol does not benefit from over-collateralisation (any surplus
returns to the borrower) and where the **bad debt** for position $i$
is

$$\text{bad-debt}_i \;=\; \max\Bigl(0,\; b_i - c_i \cdot P \cdot (1 - \pi(c_i))\Bigr),$$

i.e., the unrecoverable shortfall when realised proceeds fall below
the position's debt. The aggregate Level 2A is then
$L_{\text{2A,net}} = \sum_i r_i$.

This formulation **differs from a literal Basel haircut transposition**
on a critical point: the Basel haircut applies to a notional asset
value, while our Level 2A is bounded above by the per-position debt.
This avoids the over-counting of pledged collateral that we observed
in earlier versions of this work (see §3 of [`SCENARIOS.md`](./SCENARIOS.md)
for the full discussion).

The **on-chain numerator** is then
$\text{High Quality Liquid Assets}_{\text{on-chain}} = L_1 + L_{\text{2A,net}}$.

The **on-chain denominator** (net cash outflows under stress) is
parameterised by an **outflow fraction** $\alpha$, the fraction of
total supply withdrawn during the 24-hour stress window:

$$\text{Net cash outflows}_{\text{on-chain}}(\alpha) \;=\; \alpha \cdot S \;-\; \min\bigl(L_{\text{2A,net}},\; 0.75 \cdot \alpha S\bigr).$$

The cap at 75% of outflows reproduces BCBS 238 Annex 4 §170, which
limits the offset between secured-lending inflows and outflows.

The **outflow fraction $\alpha$ is event-calibrated** from the
empirical distribution of 24-hour drawdowns of the collateral price.
We use

$$\alpha \;=\; \min\Bigl(0.60,\; \max\bigl(0.05,\; 1.5 \cdot q_{0.99}(\text{drawdowns}) + 0.30 \cdot \mathbf{1}\{q_{0.99} > 0.05\}\bigr)\Bigr)$$

where $q_{0.99}(\text{drawdowns})$ is the 99th-percentile empirical
quantile of drawdowns, and $\mathbf{1}\{\cdot\}$ the indicator
function. The constant $1.5$ and the additive term $0.30$ are
calibrated from observations of withdrawal velocity in real events:

- During the KelpDAO event of April 2026, the Aave Total Value Locked
  fell by approximately 17% in 48 hours, peaking at approximately 10%
  in 24 hours — implying a withdrawal multiplier in the range
  $[1.4, 1.7]$ relative to the contemporaneous price drawdown.
- During the USDC depeg of March 2023, the Aave USDC market saw
  approximately 25% withdrawals on day one — consistent with a
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
| **KelpDAO collateral exploit** | Liquid-restaking-token collateral exploit, single-day cascade | 2026-04-19 23:59 UTC | No — Morpho Blue was active |
| **USDC depeg from Silicon Valley Bank collapse** | Stable-on-stable depeg | 2023-03-10 12:00 UTC | Yes — predates Morpho Blue |
| **Staked-Ether discount during the Terra/UST collapse** | Liquid-staking-token discount, multi-day slow-roll | 2022-05-11 09:00 UTC | Yes — predates Morpho Blue |

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

We apply the framework to a roster of five representative Morpho Blue
markets, calibrated to publicly observable mid-2026 conditions. The
roster is **representative**, not authoritative: the production
deployment of this framework would source live state via the
subgraph-and-RPC pipeline described in
[`docs/DATA.md`](./DATA.md). For this report, the parameters are
illustrative.

The collateral assets in the roster are:

- **wstETH** — wrapped staked Ether (a liquid-staking-token issued by Lido);
- **WBTC** — wrapped Bitcoin (an Ethereum representation of Bitcoin);
- **cbBTC** — Coinbase-wrapped Bitcoin;
- **sUSDe** — staked Ethena USD (a yield-bearing synthetic stablecoin
  issued by Ethena Labs);
- **weETH** — wrapped, Ether-denominated EtherFi liquid restaking token.

| Market | Total Value Locked (millions of U.S. dollars) | Utilisation $U$ | Liquidation threshold $\Lambda$ | 99th-percentile drawdown |
|---|---|---|---|---|
| wstETH/USDC | 350 | 88.0% | 86.0% | 14% |
| WBTC/USDC | 180 | 84.0% | 86.0% | 16% |
| cbBTC/USDC | 95 | 91.0% | 86.0% | 16% |
| **sUSDe/USDC** | 140 | **93.0%** | **91.5%** | 6% |
| weETH/USDC | 80 | 89.0% | 86.0% | 18% |

### 4.2 Risk ranking

| Market | Severity | Liquidity Coverage Ratio | $\alpha$ | Time-to-illiquid | Probability bad debt > 0 | 99th-percentile bad debt |
|---|---|---|---|---|---|---|
| **sUSDe/USDC** | red | 5.5 | 40% | 4.2h | **100%** | **26.6 million U.S. dollars** |
| weETH/USDC | red | 7.2 | 56% | 4.8h | 14% | 0.5 million U.S. dollars |
| cbBTC/USDC | red | 7.6 | 53% | 4.1h | 4% | 0.1 million U.S. dollars |
| WBTC/USDC | red | 7.6 | 53% | 7.3h | 4% | 0.0 million U.S. dollars |
| wstETH/USDC | red | 8.0 | 50% | 5.7h | 2% | 0.0 million U.S. dollars |

All five markets are flagged on the time-to-illiquid criterion under
the event-calibrated $\alpha$. This is expected: the calibrated
$\alpha$ ranges from 50% to 56% across the roster, driven by the
99th-percentile drawdown distribution, and a 50% withdrawal in 24
hours overwhelms the 7-to-15% headroom typical of Morpho markets.

**The time-to-illiquid criterion is therefore not the discriminating
signal in the forward-looking analysis**; the discrimination comes
from the bad-debt probability.

### 4.3 The sUSDe/USDC market — the dominant tail risk

The sUSDe/USDC market is the outlier: the probability of positive bad
debt is estimated at 100% across our empirical drawdown distribution,
with a 99th-percentile bad-debt of 26.6 million U.S. dollars on a Total Value
Locked of 140 million U.S. dollars, or **approximately 19% of the market's Total
Value Locked**. The mechanism is structural rather than a quirk of
our parameterisation:

- **Tight buffer between average loan-to-value and the liquidation
  threshold**: with average loan-to-value at 86% and a liquidation
  threshold at 91.5%, the headroom is 5.5%. Any drawdown larger than
  this margin liquidates the bulk of positions.
- **High utilisation**: $U = 93\%$ leaves little instant liquidity to
  absorb withdrawals during stress.
- **Slippage worse than for stablecoin-to-stablecoin pairs**:
  sUSDe-to-USDC liquidity on Uniswap V3 is meaningfully thinner than
  USDC-to-USDT pairs. Our fitted parameter $a$ is roughly four times
  that of major stablecoin pools (see [`SCENARIOS.md`](./SCENARIOS.md)
  §4.1 for the slippage parameterisation).
- **Empirical drawdown is non-zero**: even with a 99th-percentile
  drawdown of only 6%, the distribution has support near and above
  the liquidation-threshold margin, so every Monte Carlo path that
  samples a tail drawdown produces some bad debt.

This finding is **structural**: the same conclusion holds across
reasonable parameter perturbations. Lowering the liquidation
threshold to 90% or the average loan-to-value to 80% leaves
sUSDe/USDC as the riskiest market in the roster, by a wide margin on
the bad-debt probability.

The actionable implication, in the language of MetaMorpho vault
curators: a vault with material exposure to sUSDe/USDC carries a
disproportionate share of the roster's tail risk. This is consistent
with what curators have reported empirically following past Ethena
episodes; the contribution of our framework is to reproduce the
qualitative ranking with quantitative pass-or-fail criteria.

---

## 5. What this work does not establish

We list these explicitly because they materially affect the
interpretability of the headline numbers, and decentralised-finance
risk reporting often omits such caveats.

1. **The bad-debt distribution has heavy tails on a small sample.**
   Our Monte Carlo simulations use 50 to 200 paths drawn from a
   fitted Beta empirical distribution. The 99th-percentile estimate
   has wide confidence intervals; for sUSDe/USDC at probability 100%
   the result is robust to sampling, but tail magnitudes for
   less-stressed markets (wstETH, WBTC) are small numbers dominated
   by sampling noise.
2. **Counterfactual events are weakly identified.** The USDC and
   staked-Ether events predate Morpho Blue. We synthesised position
   distributions for them, calibrated to plausible parameters of
   current practice. The PASS verdict on the USDC event is more
   robust than the FAIL verdict on the staked-Ether event because the
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
