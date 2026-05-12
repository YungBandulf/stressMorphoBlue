# Stress Scenarios: Formal Specification

> Version: 0.2. Last updated: May 2026
> Status: Phase 1 deliverable. formalisation of S1 through S5 prior to implementation
> Companion documents: [`METHODOLOGY.md`](./METHODOLOGY.md);
> [`GLOSSARY.md`](./GLOSSARY.md). definitions of all specialised terms.

---

## A note on terminology

This document defines every specialised term either at first use or in
[`GLOSSARY.md`](./GLOSSARY.md). Mathematical symbols are introduced
with their units. Abbreviations are spelled out on first use, with the
abbreviation in parentheses; the abbreviation may be used thereafter
within the same section.

---

## 1. Notation and state variables

### 1.1 Per-market state vector

For a Morpho Blue lending market $M$ at block $t$, the *state vector*
is the tuple

$$x(M, t) = \left( S_t, B_t, L_t, U_t, C_t, P_t, \{(b_i, c_i)\}_i, \{s_j\}_j \right).$$

The components are defined in the table below. All quantities are
denominated in their natural units; conversions to U.S.-dollar
notional are computed only at the report stage.

| Symbol | Definition | Units |
|---|---|---|
| $S_t$ | Total supply of the loan asset, denoted `total_supply_assets` on-chain | Loan-asset units |
| $B_t$ | Total borrow of the loan asset, denoted `total_borrow_assets` on-chain | Loan-asset units |
| $L_t = S_t - B_t$ | Available liquidity (instantaneous) | Loan-asset units |
| $U_t = B_t / S_t$ | Utilisation, the fraction of supply that is borrowed | Dimensionless, $\in [0, 1]$ |
| $C_t$ | Aggregate collateral pool | Collateral-asset units |
| $P_t$ | Oracle-reported price of one collateral unit | Loan-asset per collateral unit |
| $\{(b_i, c_i)\}_i$ | Per-position pairs: borrower $i$'s debt $b_i$ and collateral $c_i$ | Loan-asset and collateral-asset units respectively |
| $\{s_j\}_j$ | Per-supplier balances | Loan-asset units |

### 1.2 Market constants (immutable per Morpho Blue's design)

The following are fixed at market creation and cannot be changed:

- $\Lambda \in [0, 1]$: the *liquidation loan-to-value threshold* (see
  [`GLOSSARY.md`](./GLOSSARY.md)). A position is liquidatable when its
  loan-to-value exceeds $\Lambda$.
- The *interest rate model*, a function $U \mapsto (r_{\text{borrow}}, r_{\text{supply}})$ mapping utilisation to a borrow rate and a
  supply rate.
- The *oracle source*: one of {Chainlink, Pyth, Redstone,
  Time-Weighted Average Price from Uniswap V3, composite} (see
  §3.S3 below for the implications of each choice).

### 1.3 Auxiliary functions

- The *slippage curve* $\pi(C, V)$: the relative shortfall (in $[0, 1]$) between the oracle-quoted price and the realised execution
  price for selling $V$ units of collateral $C$ on a decentralised
  exchange. Calibrated empirically (see §4 below).
- The *per-position loan-to-value* (already defined in
  [`GLOSSARY.md`](./GLOSSARY.md)):

 $$\text{LTV}_i(t) = \frac{b_i}{c_i \cdot P_t}.$$

 Position $i$ is *liquidatable* at block $t$ if and only if
 $\text{LTV}_i(t) > \Lambda$.

---

## 2. Stress operator framework

### 2.1 Definition

A *stress scenario* is a quadruple

$$\sigma = (\delta, T, h, \rho)$$

where:

- $\delta : \mathcal{X} \to \mathcal{X}$ is the *shock function*
  applied to the state at block $t$ (here $\mathcal{X}$ denotes the
  state space, the set of all possible state vectors);
- $T \in \mathbb{N}$ is the *shock duration* in blocks;
- $h \in \mathbb{N}$ is the *observation horizon* in blocks (with
  $h \geq T$);
- $\rho$ is the *behavioural rule* governing the evolution of the
  state from block $t$ to block $t + h$.

The output of applying $\sigma$ to an initial state $x(M, t)$ is a
*stress trajectory*

$$\mathcal{T}(M, \sigma) = \{x(M, t + k)\}_{k = 0, \ldots, h}$$

from which we compute *output metrics* $\mathcal{M}(\sigma)$ such as
the on-chain Liquidity Coverage Ratio at horizon, the time-to-illiquid,
or the realised bad debt.

### 2.2 Two execution modes

For each scenario we define both:

- **Point mode (baseline)**: the shock function $\delta$ is
  *deterministic*, calibrated to an empirical quantile of historical
  observations (typically the 99th percentile);
- **Monte Carlo mode**: the shock function $\delta$ is sampled from
  $F_\delta$, the *empirical cumulative distribution function* of
  historical observations. We simulate $N$ paths and report metrics as
  the tuple (mean, 5th percentile, 95th percentile, 99th percentile).

This dual structure means Monte Carlo support is **architectural**,
not an afterthought. Any implementation that closes the door on Monte
Carlo violates the specification.

### 2.3 Behavioural regimes

- **Exogenous regime (baseline)**: liquidator selling on the
  decentralised exchange does not move the oracle price; it only
  affects collateral recovery.
- **Endogenous regime**: liquidator selling on the decentralised
  exchange moves the exchange price; if the market's oracle is
  decentralised-exchange-derived (such as the Time-Weighted Average
  Price from Uniswap V3), the feedback activates.

The choice of regime is **per-market**, driven by the oracle
configuration. Markets using Chainlink with off-chain aggregation
default to the exogenous regime; markets using a Time-Weighted
Average Price from Uniswap V3 default to the endogenous regime.

---

## 3. Scenarios

### S1: Withdrawal run

**Description**: a fraction $\alpha$ of suppliers attempt to withdraw
their balance over duration $T$.

**Shock function $\delta_{S1}$**:

$$W_{\text{requested}}(\tau) = \alpha \cdot S_t \cdot w(\tau), \qquad \tau \in [t, t + T]$$

where $w(\tau)$ is a *withdrawal-arrival pattern* (default: linear,
$w(\tau) = 1/T$; sensitivity test: front-loaded exponential).

**Calibration of $\alpha$**:

- *Point mode*:
  $\alpha = q_{0.99}\left(\sum_j \Delta s_j^- / S\right)$
  over rolling 24-hour windows, per market, on the 12-month historical
  sample. Here $\Delta s_j^-$ denotes the negative changes in supplier
  $j$'s balance (i.e. withdrawals).
- *Monte Carlo mode*: $\alpha \sim F_\alpha^{\text{empirical}}$, the
  empirical cumulative distribution function of the same series.

**Behavioural rule $\rho_{S1}$**:

A withdrawal request at block $\tau$ is honoured if and only if
$L_\tau \geq W_{\text{requested}}(\tau)$. Otherwise:

- The honoured portion equals $\min\left(W_{\text{requested}}(\tau), L_\tau\right)$;
- The unhonoured portion accumulates in a *queued register*;
- The supplier is recorded as *queued* for accounting purposes.

Optional response: if `behavior = 'rate_response'`, an interest-rate
spike (caused by the rising utilisation that follows withdrawals)
triggers borrower repayment proportional to the rate gap times an
elasticity. Default at baseline: no response (conservative).

**Output metrics**:

- *Time-to-illiquid*: $\min\{\tau : L_\tau = 0 \wedge \mathrm{queued}_\tau > 0\}$, or infinity if never;
- *Total queued at horizon*: cumulative unhonoured withdrawals at
  block $t + h$;
- *Stuck ratio*: $\text{total queued} / (\alpha \cdot S_t)$.

---

### S2: Utilisation spike

**Description**: borrow demand spikes; new borrowers enter the market
over $T$ blocks.

**Shock function $\delta_{S2}$**:

$$\Delta B_{\text{requested}}(\tau) = \beta \cdot S_t \cdot w(\tau), \qquad \tau \in [t, t + T]$$

with new borrowers entering at loan-to-value equal to $\Lambda - \varepsilon$ for a small $\varepsilon$ (worst-case borrower behaviour;
this tightens the position-health distribution).

**Calibration of $\beta$**:

- *Point mode*: $\beta = q_{0.99}(\Delta B^+ / S)$ over rolling
  24-hour windows.
- *Monte Carlo mode*: $\beta \sim F_\beta^{\text{empirical}}$.

**Behavioural rule $\rho_{S2}$**:

- New borrows fill until $U = 1$ (full utilisation); excess demand is
  unsatisfied.
- The interest rate model raises $r_{\text{borrow}}$. Supplier inflow
  is modelled as $\Delta S^+ = \eta \cdot \max(0, r_{\text{borrow}} - r_{\text{benchmark}})$ if
  `behavior = 'rate_response'`, else null. Here $\eta$ is the
  *supplier-rate elasticity*, a calibrated parameter.
- Position-level: new borrowers' loan-to-value approaches $\Lambda$,
  so a subsequent S3-style oracle move would liquidate them, an
  explicit linkage to S4.

**Output metrics**:

- *Peak utilisation*: $\max_\tau U_\tau$ over the horizon;
- *Unsatisfied borrow demand at horizon*;
- *Rate trajectory*: the full path of $r_{\text{borrow}}(\tau)$;
- *Induced fragility*: fraction of new positions with $\text{LTV} > 0.95 \cdot \Lambda$, these positions feed the input to S4.

---

### S3: Oracle deviation

**Description**: the collateral price drops by $\Delta$ over a window
$\Delta t$; the oracle reports a possibly-lagged price.

**Shock function $\delta_{S3}$**: two coupled price paths are
generated.

- *Market price path*:

 $$P_\tau^{\text{market}} = P_t \cdot \left(1 - \Delta \cdot g(\tau)\right), \qquad \tau \in [t, t + \Delta t]$$

 where $g(\tau)$ is a *drawdown shape* (linear by default, instant
 step for shock test).

- *Oracle price path*:

 $$P_\tau^{\text{oracle}} = \mathrm{TWAP}_\lambda\left(P_\cdot^{\text{market}}, \tau\right)$$

 where $\mathrm{TWAP}_\lambda$ denotes the geometric Time-Weighted
 Average Price over a window of $\lambda$ blocks (the oracle's
 smoothing window, read from the contract configuration).

**Calibration**:

- $\Delta$ in *point mode*: $\Delta = q_{0.99}(\text{drawdown over }\Delta t)$
  from the oracle-or-market historical price series of the
  collateral asset;
- $\Delta$ in *Monte Carlo mode*: $\Delta \sim F_\Delta^{\text{empirical}}$,
  fitted on the rolling drawdown distribution;
- Three values of $\Delta t$ in parallel: 1 hour, 24 hours, 7 days;
- $\lambda$ deterministic, read from the oracle's on-chain
  configuration.

**Behavioural rule $\rho_{S3}$**:

At each block $\tau$:

1. Update the per-position loan-to-value:
  $\text{LTV}_i(\tau) = b_i / (c_i \cdot P_\tau^{\text{oracle}})$;
2. Identify the set of liquidatable positions
  $\mathcal{L}_\tau = \{i : \text{LTV}_i(\tau) > \Lambda\}$;
3. Liquidate positions in $\mathcal{L}_\tau$ with realistic latency
  $\delta_{\text{liq}}$ (default: 2 blocks);
4. Recovery accounting per liquidation $i$:

 $$R_i = c_i \cdot P_\tau^{\text{market}} \cdot \left(1 - \pi(C, c_i)\right)$$

 $$\text{shortfall}_i = \max\left(0, b_i - R_i\right).$$

 Liquidation pricing uses the **market price**, not the oracle
 price, and slippage is computed via $\pi$.

**Output metrics**:

- *Number liquidated*: count of positions liquidated at horizon;
- *Bad debt*: $\sum_i \text{shortfall}_i$;
- *Slippage shortfall*: gap between oracle-priced and realised
  recovery, $\sum_i \max(0, c_i \cdot P_\tau^{\text{oracle}} - R_i)$.

---

### S4: Liquidation cascade (composite)

**Description**: oracle drop combined with liquidations and
decentralised-exchange slippage feedback. Unlike S3, the *endogenous
regime* is the **default**, cascade is the point of the scenario.

**Shock function $\delta_{S4}$**: joint shock $(\Delta, \Delta t)$ calibrated at the 95th percentile *jointly*. The 99th-percentile
joint is unreliable on a 12-month sample.

**Behavioural rule $\rho_{S4}$**:

Endogenous feedback, liquidator selling moves the
decentralised-exchange price; if the oracle is
decentralised-exchange-derived, the oracle follows. Update equation:

$$P_{\tau+1}^{\text{market}} = P_\tau^{\text{market}} \cdot \left(1 - \pi(C, V_{\text{liquidated}}(\tau))\right)$$

where $V_{\text{liquidated}}(\tau)$ is the volume sold by liquidators
in block $\tau$. If the oracle is Time-Weighted-Average-Price-based:

$$P_{\tau+1}^{\text{oracle}} = \mathrm{TWAP}_\lambda\left(P_\cdot^{\text{market}}, \tau + 1\right).$$

Otherwise (Chainlink or other off-chain oracle), the oracle path
remains as in S3 (no feedback).

**Iteration order per block**:

1. Accrue interest;
2. Update the oracle price (with potential feedback from the previous
  block);
3. Identify liquidatable positions;
4. Execute liquidations (computing slippage on the aggregate volume
  sold this block);
5. Update the decentralised-exchange price reflecting cumulative
  selling;
6. Move to the next block and return to step 1.

This sequential structure prevents within-block circularity. A more
sophisticated model would solve a fixed point per block.

**Output metrics**:

- *Total bad debt* (point mode: scalar; Monte Carlo mode:
  distribution);
- *Cascade depth*: $\max_\tau |\mathcal{L}_\tau|$, the maximum number
  of simultaneous liquidations in any single block;
- *Realised slippage*: average and worst-block $\pi$ realised;
- *Feedback amplification*: the ratio of (endogenous cascade bad debt)
  to (exogenous-counterfactual bad debt), measures the cost of the
  feedback.

---

### S5: KelpDAO replay (event-driven)

**Description**: counterfactual replay of the April 2026 KelpDAO event
applied to current Morpho Blue state.

**Shock function $\delta_{S5}$**: reconstruct the historical
price-and-event path from on-chain data covering 19 April through 22
April 2026. Apply this path as $P_\tau^{\text{market}}$ for the
affected collateral types. For unaffected collateral types, no shock
is applied.

**Behavioural rule $\rho_{S5}$**: as in S4 (endogenous
cascade), with the historical path replacing the synthetic drawdown.

**Output metrics**:

- *Counterfactual bad debt* per market under the worst-event-of-2026
  conditions;
- *Comparison ratio*: bad debt under KelpDAO replay divided by bad
  debt under S4 at the 95th-percentile joint shock.

This scenario is **the validation anchor** of the framework: a
credible model should flag fragility in markets that, if they had
existed identically in April 2026, would have suffered.

---

## 4. Calibration plan

### 4.1 Sources

| Parameter | Source | Method | Notes |
|---|---|---|---|
| $\alpha$ (S1) | Subgraph `Withdraw` events | Empirical 99th-percentile quantile over rolling 24 hours, per market | Minimum 6-month sample for stable estimate |
| $\beta$ (S2) | Subgraph `Borrow` events | Empirical 99th-percentile quantile over rolling 24 hours | Same minimum sample |
| $\Delta$ (S3, S4) | Oracle price feed | Empirical 99th-percentile negative log-return over $\Delta t$ | Per collateral; cross-checked against centralised-exchange price |
| $\lambda$ (S3) | On-chain oracle configuration | Read directly from contract | Chainlink heartbeat or Time-Weighted Average Price window |
| $\pi(C, V)$ | Decentralised-exchange trades and 1inch quotes | Fit power law $\pi(V) = a \cdot V^b$ via ordinary least squares regression in log-space; fallback to lookup | Validate fit per asset |
| KelpDAO path (S5) | On-chain data, 19 April through 22 April 2026 | Direct extraction, no fitting | Anchor event |

### 4.2 Statistical caveat (important)

A 12-month window with rolling 24-hour observations gives
approximately 365 disjoint observations or approximately 8,760
overlapping observations. The 99th-percentile quantile is therefore
estimated from approximately 3 disjoint or 88 overlapping tail
observations.

**Confidence intervals on the 99th-percentile are wide**, particularly
for assets with limited history (such as sUSDe and cbBTC). This is an
unavoidable baseline weakness, addressed by:

- Reporting bootstrap confidence intervals on each calibrated
  quantile;
- Using overlapping windows (with adjusted standard errors) where the
  stationarity assumption is plausible;
- Sensitivity tests at the 95th and 99.5th percentiles alongside the
  99th.

---

## 5. Monte Carlo mode (retained baseline extension)

### 5.1 Sampling

For each scenario, the Monte Carlo mode samples shock parameters as
follows.

```python
def stress_scenario_mc(scenario: Scenario, x0: State,
 n_paths: int = 10_000, seed: int = 42) -> McResult:
 rng = np.random.default_rng(seed)
 metrics = []
 for _ in range(n_paths):
 sampled_shock = scenario.empirical_distribution.sample(rng)
 traj = simulate(scenario, x0, shock=sampled_shock)
 metrics.append(extract_metrics(traj))
 return McResult.aggregate(metrics)
```

### 5.2 Reported aggregates

For each metric: mean, standard deviation, 5th, 50th, 95th, and 99th
percentiles.

### 5.3 Concrete Monte Carlo use cases

1. **Bad debt distribution under S4**: expectation, 95th and 99th
  percentiles of bad debt. Headline number for a market's tail risk.
2. **Time-to-illiquid under S1**: median, interquartile range,
  probability that time-to-illiquid is less than 24 hours.
3. **Joint scenario Value-at-Risk**: combine S3 and S1 (oracle drop
  plus supplier panic) as a compound event; estimate the 99% liquidity
  Value-at-Risk, defined as the 99th-percentile of the net liquidity
  gap.

### 5.4 Computational budget

- One trajectory at $h = 30$ days: approximately 216,000 blocks
  (Ethereum), optimised to approximately 2,500 effective steps with
  sparse position updates → approximately 0.5 to 2 seconds in
  vectorised Python;
- 10,000 Monte Carlo paths × 5 markets × 5 scenarios = 250,000
  trajectories;
- Single-machine estimate: 35 to 140 hours;
- **Plan B**: 1,000 paths as a baseline (3.5 to 14 hours) plus 10,000
  paths only on markets and scenarios flagged red. Recommended default
  for the baseline run.
- Parallelisation via `joblib` over CPUs gives a 5-to-8-fold speedup
  on a workstation.

### 5.5 Distributional-assumption health check

Empirical distributions on 12 months are **weak in the tail** ,
particularly for assets with short history. Mitigations:

- *Block bootstrap* with 24-hour block size to preserve
  autocorrelation;
- *Tail Pareto fit* for $\Delta$ as a sensitivity test;
- *Cross-asset pooling* for $\pi$ where collateral types share
  liquidity venues.

---

## 6. Validation strategy

### 6.1 Backtest validation (KelpDAO ex-ante)

Apply the framework retrospectively at $t_0$ = 18 April 2026 (one day
before the KelpDAO event). The framework **passes** if, for affected
markets, at least one of the following holds:

- $\mathrm{LCR_{oc}}(M, t_0, \sigma_{S5}, h = 24\text{h}) < 100\%$;
- *Time-to-illiquid* $(M, \sigma_{S1,q_{0.99}}, h = 24\text{h}) < 24$ hours;
- $\Pr[\text{bad debt} > 0 \mid \sigma_{S4}] > 5\%$,

is satisfied **before** the event timestamp.

If the framework fails this test (no flag), one of three things is
wrong:

1. The framework is mis-calibrated;
2. The event was unforeseeable from on-chain data alone (the
  academically interesting outcome);
3. The specification has a bug.

We commit to reporting all three honestly.

### 6.2 Cross-check with public risk reports

For markets with risk scores published by Gauntlet, ChaosLabs, or
LlamaRisk in the same window, compute the *Spearman rank correlation*
between our $\mathrm{LCR_{oc}}$ ranking and theirs.
Expected: Spearman $\rho > 0.5$. Lower correlation either reflects
genuine differentiation or model error; the writeup must explain
which.

### 6.3 Sanity tests (smoke tests)

- Markets with $U_{t_0} < 50\%$ and well-funded suppliers should
  *never* reach illiquidity under $\sigma_{S1}$ at the
  99th-percentile $\alpha$. If they do, model bug.
- Markets with collateral on Curve-or-Uniswap deep liquidity should
  have *lower* realised $\pi$ than markets with thin
  liquid-restaking-token or real-world-asset collateral. If the
  ordering inverts, the slippage fit has a bug.
- The framework should be **monotonic in stress severity**: more
  stress yields worse metrics. Non-monotonicity indicates a bug.

---

## 7. Output schema (per market × scenario × horizon)

| Metric | Type | Format | Threshold |
|---|---|---|---|
| $\mathrm{LCR_{oc}}$ | float | percentage | green $\geq 150\%$ / yellow $\in [100\%, 150\%)$ / red $< 100\%$ |
| Time-to-illiquid | int | blocks (or null) | \text{green } \geq 7\text{d} \text{ / yellow } \in [24\text{h}, 7\text{d}) \text{ / red } < 24\text{h} |
| Expected bad debt | float | U.S. dollars (point mode: scalar; Monte Carlo: distribution) | green 0 / yellow $< 1\%$ Total Value Locked / red $\geq 1\%$ |
| Slippage shortfall | float | U.S. dollars | reported, no threshold |
| Cascade depth | int | count | reported, no threshold |
| Feedback amplification | float | ratio | reported, no threshold |
| Severity flag | enum | green / yellow / red | composite of the above |

---

## 8. Implementation roadmap (forward references)

| Phase | Item | Dependency |
|---|---|---|
| 2 | Data acquisition (subgraph, RPC, decentralised exchange) |, |
| 2 | Interest rate model, oracle, slippage models implemented | Phase 2 data |
| 3 | S1, S2, S3 standalone | Phase 2 |
| 3 | S4 cascade (both regimes) | S3 |
| 3 | S5 KelpDAO replay | S4 |
| 3 | Monte Carlo mode for all scenarios | Point mode complete |
| 4 | Validation per §6 | All scenarios |
| 5 | Forward-looking application on top-five markets | Phase 4 pass |

---

## 9. Document version control

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-04 | Initial Phase 1 deliverable |
| 0.2 | 2026-05-05 | All abbreviations spelled out at first use; companion `GLOSSARY.md` published |
