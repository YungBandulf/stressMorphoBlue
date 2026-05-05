# Methodology — Liquidity Stress Testing Framework for Morpho Blue

> Version: 0.3 — Last updated: May 2026
> Status: Phase 0 deliverable — methodological note (revised through Phase 5)
> Companion: [`SCENARIOS.md`](./SCENARIOS.md) — stress-scenario specifications;
> [`GLOSSARY.md`](./GLOSSARY.md) — definitions of all specialised terms.
> Author: PA

---

## A note on terminology

This document defines every specialised term either at first use or in
[`GLOSSARY.md`](./GLOSSARY.md). Mathematical symbols are introduced
with their units. Abbreviations are spelled out on first use, with the
abbreviation in parentheses, and used as the abbreviation thereafter
within a single section.

---

## 1. Research question

### 1.1 Primary hypothesis (falsifiable)

We adopt the Popperian standard: a primary hypothesis is a claim
formulated such that observations could refute it.

Given the on-chain state of a Morpho Blue lending market $M$ at block
$t$ — characterised by the tuple
$(S_t, B_t, \Lambda, \text{oracle}, \text{interest rate model}, \pi)$
where $S_t$ is total supply (loan-asset units), $B_t$ is total borrow
(loan-asset units), $\Lambda$ is the liquidation loan-to-value
threshold (a market parameter, $\in [0,1]$), and $\pi$ is the
slippage curve of the collateral on the relevant decentralised
exchange — there exists a stress scenario $\sigma$ such that, at
horizon $h$ blocks, the market enters one of two distress states:

- **Illiquid state**: incapacity to satisfy supplier withdrawal demand
 at block $t + h$, formally:
 $W_{\text{requested}}(t, t+h) > L(t+h)$
 where $W_{\text{requested}}$ is cumulative requested withdrawals and
 $L = S - B$ is the available liquidity.

- **Insolvent state**: realised bad debt $B_{\text{bad}}(t+h) > 0$,
 meaning that liquidations failed to fully cover defaulted positions
 due to collateral price gaps, oracle deviation, or liquidator
 decentralised-exchange slippage.

The probability of these states is bounded **empirically** from a
12-month rolling historical window, calibrated on observed stress
events (the KelpDAO collateral exploit of April 2026, the USDC depeg
of March 2023, and the staked-Ether discount episode of May 2022).

### 1.2 Secondary hypothesis (vault-curator angle)

For a MetaMorpho vault $V$ with curator $c$ at block $t$, define the
**risk-discipline gap**:

$$\Delta(V, t) = \Bigl\| X_{\text{observed}}(V, t) - X^\star(V, t) \Bigr\|_2$$

where:
- $X_{\text{observed}}$ is the curator's actual allocation vector
 across approved Morpho Blue lending markets, indexed by market
 identifier;
- $X^\star$ is the theoretical allocation that minimises 30-day
 liquidity Value-at-Risk under the stress framework defined in this
 document;
- $\|\cdot\|_2$ denotes the Euclidean norm.

To our knowledge, $\Delta$ is the first quantitative measure of curator
risk discipline in decentralised-finance literature. Existing risk
reports (from Gauntlet, Block Analitica, ChaosLabs and others) publish
absolute risk reports on individual markets but do not explicitly
compute curator counterfactuals.

### 1.3 Why this matters

- **Academic gap**: Chiu, Ozdenoren, Yuan and Zhang (Bank for
 International Settlements Working Paper 1062, 2023) show that
 decentralised-finance lending pools are inherently fragile, but
 published work focuses on monolithic pools (Aave, Compound). Morpho
 Blue's *isolated-market design* — in which each market is an
 immutable tuple sharing no liquidity with others — has no comparable
 formal stress-testing framework.

- **Industry gap**: Risk reports from Gauntlet, Block Analitica and
 LlamaRisk transpose Basel concepts informally. We provide an
 **explicit Basel III mapping** with stated limitations.

- **Timing**: The KelpDAO event of April 2026 generated approximately
 196 million U.S. dollars in bad debt on Aave and approximately 8 billion U.S. dollars of
 capital migration to Morpho. This is the largest stress event of
 the present cycle and provides a calibration anchor that did not
 exist before.

---

## 2. Theoretical framework

### 2.1 Adaptation of the Liquidity Coverage Ratio

The Liquidity Coverage Ratio defined by the Basel Committee on Banking
Supervision (the *Basel Committee* hereafter) in document BCBS 238
(2013) is

$$\text{Liquidity Coverage Ratio} = \frac{\text{High Quality Liquid Assets}}{\text{Net cash outflows over 30 days}} \geq 100\%.$$

The **High Quality Liquid Assets** (the numerator, abbreviated *HQLA*
in this document for brevity from now on) are defined by the Basel
Committee in three tiers:

- **Level 1**: cash, central-bank reserves, and top-rated sovereign
 debt — haircut 0% (the haircut being the fraction of value assumed
 lost on monetisation under stress).
- **Level 2A**: highly liquid corporate or covered bonds — haircut
 15%.
- **Level 2B**: lower-rated corporate or equity — haircut 25 to 50%.

The **net cash outflows** (the denominator) are computed under a
stress scenario specified by the Basel Committee, with runoff factors
(percentages of liabilities expected to be withdrawn) ranging from
5% (insured retail deposits) to 100% (unsecured wholesale funding by
financial corporates).

We construct an on-chain analogue of the Liquidity Coverage Ratio for
a Morpho Blue lending market $M$ at block $t$, denoted
$\mathrm{LCR}_{\mathrm{onchain}}(M, t, \sigma, h)$ where $\sigma$ is
the stress scenario and $h$ is the horizon in blocks:

$$\mathrm{LCR}_{\mathrm{onchain}}(M, t, \sigma, h) = \frac{L_1(M, t) \,+\, L_{2A,\mathrm{net}}(M, t, \sigma)}{O_\sigma(M, t, h) - \min\bigl(I_\sigma(M, t, h), 0.75 \cdot O_\sigma\bigr)}$$

where:
- $L_1(M, t) = S_t - B_t$ is the on-chain analogue of HQLA Level 1
 (instant liquidity, no haircut);
- $L_{2A,\mathrm{net}}(M, t, \sigma)$ is the per-position liquidation
 recovery under stress (defined in §2.2 below);
- $O_\sigma(M, t, h) = \alpha \cdot S_t$ is the stress outflow, with
 $\alpha$ event-calibrated (defined in §2.4 below);
- $I_\sigma(M, t, h)$ is the inflow from forced repayments through
 liquidations during the stress window;
- The cap at 75% reproduces BCBS 238 Annex 4 §170, which limits the
 offset between secured-lending inflows and outflows.

The mapping from Basel definitions to Morpho Blue analogues is:

| Basel component | Basel definition | Morpho Blue analogue |
|---|---|---|
| HQLA Level 1 (haircut 0%) | Cash, central-bank reserves, top sovereign debt | Instant liquidity $L_1 = S - B$ |
| HQLA Level 2A (haircut 15%) | Highly liquid corporate or covered bonds | Per-position liquidation recovery, capped at debt and discounted by stress slippage (see §2.2) |
| HQLA Level 2B (haircut 25–50%) | Lower-rated corporate or equity | Collateral with limited decentralised-exchange liquidity (exotic liquid-restaking-tokens, real-world-asset tokens), with slippage drawn from the upper tail of the empirical distribution |
| Outflows: stable retail (5%) | Insured retail deposits | Approximated by the median historical withdrawal velocity |
| Outflows: less-stable retail (10%) | Non-insured retail deposits | Approximated by the 90th-percentile historical withdrawal velocity |
| Outflows: wholesale unsecured (40–100%) | Non-financial or financial-corporate funding | Whale concentration: simultaneous withdrawal by the top-five suppliers under stress |
| Inflows: secured lending (cap 75%) | Repayments and collateral inflows | Forced repayments from liquidations during the stress window |

### 2.2 Per-position liquidation recovery (the on-chain Level 2A)

A literal application of a Basel Level 2A haircut to total collateral
notional value (i.e. $L_{\text{2A}} = 0.85 \cdot C \cdot P$ where $C$
is total collateral and $P$ the oracle price) **over-estimates the
recoverable assets**, because collateral is pledged and only
liquidatable through the protocol's liquidation procedure. The
recovery from a single position $i$ is:

1. The liquidator seizes collateral up to the *liquidation incentive
 factor* $\phi(\Lambda)$ above debt:
 $\mathrm{seized}_i = \min\bigl(b_i \cdot \phi(\Lambda) / P, c_i\bigr)$
2. The liquidator sells the seized collateral on a decentralised
 exchange at the realised price $P \cdot (1 - \pi(\mathrm{seized}_i))$;
3. The supplier pool receives loan-asset proceeds, capped at the
 position's debt $b_i$ (any surplus accrues to the borrower);
4. If proceeds fall below the debt, the shortfall is *bad debt*,
 borne by the supplier pool.

Formally, the recovery from position $i$ is

$$r_i = \min\Bigl(\mathrm{seized}_i \cdot P \cdot (1 - \pi(\mathrm{seized}_i)), b_i\Bigr) - \mathrm{BD}_i$$

where the bad debt for position $i$ is

$$\mathrm{BD}_i = \max\Bigl(0, b_i - \mathrm{seized}_i \cdot P \cdot (1 - \pi(\mathrm{seized}_i))\Bigr).$$

The aggregate Level 2A is

$$L_{2A,\mathrm{net}}(M, t, \sigma) = \sum_i r_i.$$

The **liquidation incentive factor** $\phi$ is given by Morpho Blue's
formula

$$\phi(\Lambda) = \min\Bigl(1.15, \frac{1}{0.3 \cdot \Lambda + 0.7}\Bigr),$$

capping the bonus at 15% above debt for low values of $\Lambda$. For
$\Lambda = 0.86$ (typical for major asset–stablecoin pairs), $\phi$
is approximately $1.043$.

### 2.3 Honest critique of the adaptation

The mapping in §2.1 is non-trivial; several choices are defensible
but not unique. We list the tensions explicitly:

1. **Time-unit mismatch**: the Basel Committee reasons in months;
 on-chain we measure in blocks (12 seconds on Ethereum). The Basel
 parameter $h = 30$ days is not natural; we expose $h$ as a free
 parameter and report results at three horizons: 24 hours, 7 days,
 30 days.

2. **No equivalent of "stable funding"**: in decentralised-finance
 lending, all suppliers are 100% callable by construction. The
 Basel concept of "operational deposits" has no on-chain analogue.
 We therefore expect that *all decentralised-finance lending pools
 have a structurally low Net Stable Funding Ratio* by Basel
 standards (see §2.5 below). The Liquidity Coverage Ratio is most
 informative *relative to itself* across markets and over time, not
 in absolute terms.

3. **Oracle as exogenous**: we treat oracle prices as exogenous
 inputs in the baseline. In reality, oracle behaviour
 (time-weighted-average-price smoothing, deviation thresholds,
 fallback logic) is endogenous to the stress scenario. This is a
 deliberate baseline simplification — modelled as a sensitivity
 analysis, not a structural feature.

### 2.4 Event-calibrated outflow fraction

The outflow fraction $\alpha$ in §2.1 is *not* a Basel-style
universal constant. It is derived from each market's own price-drawdown
distribution as a proxy for withdrawal velocity:

$$\alpha = \min\Bigl(0.60, \max\bigl(0.05, 1.5 \cdot q_{0.99}(\mathrm{drawdowns}) + 0.30 \cdot \mathbf{1}\{q_{0.99}(\mathrm{drawdowns}) > 0.05\}\bigr)\Bigr)$$

where:
- $q_{0.99}(\mathrm{drawdowns})$ is the 99th-percentile empirical
 quantile of 24-hour collateral price drawdowns over the past
 rolling year, expressed as a fraction;
- $\mathbf{1}\{\cdot\}$ is the indicator function.

The constant $1.5$ and the additive 30% (the *whale-concentration
term*) are calibrated from observed withdrawal velocity in real
events, as discussed in [`REPORT.md`](./REPORT.md) §2.1.

### 2.5 The Net Stable Funding Ratio — a more discriminating angle

The Net Stable Funding Ratio defined in BCBS 295 (2014) is

$$\text{Net Stable Funding Ratio} = \frac{\text{Available Stable Funding}}{\text{Required Stable Funding}} \geq 100\%.$$

For decentralised-finance lending, a brute-force application yields:

- **Available Stable Funding weight**: suppliers are instantly
 callable, so the Available Stable Funding factor is approximately
 0%;
- **Required Stable Funding weight**: borrows have no contractual
 maturity (perpetual), so the Required Stable Funding factor is
 approximately 100%.

The Net Stable Funding Ratio is therefore approximately 0 for any
decentralised-finance lending pool. This is a **structural insight
rarely articulated in decentralised-finance risk literature**, because
crypto-native analysts typically do not work in the Basel framework.

The interesting analysis is the **conditional Net Stable Funding
Ratio**: how much funding is *empirically* stable, given oracle
health, prevailing yield differential versus alternatives, and
supplier concentration? This reduces to estimating a
*withdrawal-survival function* $S(t \mid \text{features})$, which we
model via Kaplan–Meier-style empirical cumulative distributions on
historical supplier behaviour. This is **the academic contribution of
the project** beyond the descriptive stress-test layer.

---

## 3. Scope

### 3.1 Markets

Top-five Morpho Blue lending markets by Total Value Locked on the
Ethereum mainnet at the start of the data-acquisition phase, frozen
on day one of that phase (see
[`scripts/select_markets.py`](../scripts/select_markets.py) once
implemented).

**Candidate set (subject to revalidation at run time)**:
- wstETH/USDC (collateral: wrapped staked Ether; loan asset: USDC)
- wstETH/WETH (collateral: wrapped staked Ether; loan asset: wrapped Ether)
- WBTC/USDC (collateral: wrapped Bitcoin; loan asset: USDC)
- cbBTC/USDC (collateral: Coinbase-wrapped Bitcoin; loan asset: USDC)
- sUSDe/USDC (collateral: staked Ethena USD; loan asset: USDC)

Selection criteria, in order: (i) Total Value Locked greater than
100 million U.S. dollars, (ii) market age greater than 6 months, (iii) at least
one stress event observable in the historical window.

### 3.2 Historical window

Twelve rolling months: May 2025 through May 2026. This window contains:

- The KelpDAO collateral exploit and ensuing migration of Total Value
 Locked (April 2026), used as the **primary calibration anchor**;
- A series of oracle deviations and minor depegs (continuous, low
 intensity);
- Sector-wide macro stress around the third quarter of 2025 (to
 verify at data-acquisition time).

### 3.3 Stress horizons

Three values of $h$, reported in parallel:

- **24 hours** — equivalent of an intraday liquidity squeeze;
- **7 days** — short-horizon stress;
- **30 days** — Basel-equivalent horizon.

### 3.4 Stress scenarios (four plus one)

Five scenarios, fully specified in [`SCENARIOS.md`](./SCENARIOS.md).
Summary:

| Identifier | Scenario | Description | Severity calibration |
|---|---|---|---|
| **S1** | Withdrawal run | Suppliers withdraw fraction $\alpha$ of total supply over duration $T$ | $\alpha$ at the 99th-percentile of historical withdrawal velocity, $T \in \{1\text{h}, 24\text{h}, 7\text{d}\}$ |
| **S2** | Utilisation spike | Sudden borrow demand pushes utilisation toward 1 | Spike calibrated on the top-three historical events |
| **S3** | Oracle deviation | Collateral price drops by $\Delta$ in $\Delta t$; oracle reports lagged price | $\Delta$ at the 99th-percentile of historical drawdowns over $\Delta t$ |
| **S4** | Liquidation cascade | Combination: oracle drop with liquidations and decentralised-exchange slippage feedback | All three at the 95th-percentile jointly |
| **S5** | KelpDAO replay | Backtest of the April 2026 event applied to current Morpho markets ex-post | Empirical, no parameter |

### 3.5 Output metrics

For each (market, scenario, horizon) tuple:

- $\mathrm{LCR}_{\mathrm{onchain}}$ — the primary metric, reported as
 a time series and worst-case;
- *Time-to-illiquid* — first block at which available liquidity is
 exhausted under the scenario;
- *Expected bad debt* — sum of unrecovered debt at end of horizon;
- *Slippage-adjusted shortfall* — gap between oracle-priced collateral
 and decentralised-exchange-realised recovery;
- *Withdrawal survival curve* — empirical $S(t \mid \sigma)$ for the
 secondary hypothesis.

---

## 4. Limitations (explicit and exhaustive)

1. **Endogeneity ignored at baseline**: prices, withdrawals, and
 liquidations are treated as separable processes. In reality,
 large liquidations move decentralised-exchange prices, which
 trigger more liquidations (a feedback loop). Capponi and Jia
 (2021) and follow-up work formalise this. Modelling it requires
 agent-based simulation or a fixed-point solver — out of scope at
 the baseline; flagged for a future version.

2. **Oracle as exogenous input**: time-weighted-average-price
 behaviour, fallback paths, and oracle outages are not endogenously
 modelled. Sensitivity analysis only.

3. **Maximal extractable value and liquidator competition**:
 liquidations are assumed perfect (no liquidator stuck in mempool,
 no priority-gas-auction failure). This biases bad-debt estimates
 downward at the baseline.

4. **Cross-market contagion**: by Morpho Blue design, lending markets
 are isolated, so there is no cross-market contagion at the
 protocol layer. *However*, MetaMorpho vaults link markets
 economically through curator allocation. Vault-level analysis (the
 secondary hypothesis) introduces this dimension.

5. **Calibration on a short window**: 12 months of data on a
 fast-evolving protocol means small-sample bias. Confidence
 intervals are reported but should be taken as indicative.

6. **Monte Carlo as retained extension**: scenarios are designed in
 dual mode — point (deterministic shocks at empirical quantiles)
 and Monte Carlo (sampled from empirical distributions, with $N$
 paths and confidence intervals). Monte Carlo is *not* deferred
 future work: it is part of the baseline specification (see
 [`SCENARIOS.md`](./SCENARIOS.md) §5). The honest caveat is
 statistical: a 12-month sample produces wide confidence intervals
 on tail quantiles. The 99th-percentile is estimated from
 approximately three disjoint or 88 overlapping observations.
 Block bootstrap and Pareto-tail sensitivity tests are used to
 bound this uncertainty, but tail estimation on short
 decentralised-finance history remains the dominant source of
 model risk.

7. **Solidity behaviour not simulated end-to-end**: we model the
 economic state, not gas or mempool dynamics. A full Foundry
 fork-test would close this gap.

8. **Smart-contract risk excluded**: the framework assumes Morpho
 Blue contracts execute correctly. Contract-level risk (bugs,
 governance attacks) is out of scope.

---

## 5. References

See [`references.md`](./references.md) for the full bibliography. Core
anchors:

- **Basel framework**: BCBS 238 (Liquidity Coverage Ratio, 2013); BCBS
 295 (Net Stable Funding Ratio, 2014).
- **Decentralised-finance lending theory**: Gudgeon, Werner, Perez and
 Knottenbelt (2020); Capponi and Jia (2021, 2023); Chiu, Ozdenoren,
 Yuan and Zhang (Bank for International Settlements Working Paper
 1062, 2023).
- **Protocol specification**: Morpho Labs, *Morpho Blue Whitepaper*
 and *Morpho Blue Yellow Paper*.
- **Industry benchmarks**: Steakhouse Financial public Maker
 analyses; Block Analitica risk reports; LlamaRisk Aave and Curve
 reports.

---

## 6. Document version control

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-04 | Initial draft (Phase 0) |
| 0.2 | 2026-05-04 | §4.6 — Monte Carlo retained as baseline extension; companion `SCENARIOS.md` published |
| 0.3 | 2026-05-05 | All abbreviations spelled out at first use; per-position liquidation recovery (§2.2) introduced; companion `GLOSSARY.md` published |
