# Stress Scenarios — Formal Specification

> Version: 0.1 (draft) — Last updated: May 2026
> Status: Phase 1 deliverable — formalization of S1–S5 prior to implementation
> Companion document: [`METHODOLOGY.md`](./METHODOLOGY.md)

---

## 1. Notation and State Variables

### 1.1 Per-market state vector

For a Morpho Blue market $M = (\text{collateral}, \text{loanAsset}, \text{oracle}, \text{IRM}, \text{LLTV})$ at block $t$, the state vector is:

$$x(M, t) = \big( S_t,\ B_t,\ L_t,\ U_t,\ C_t,\ P_t,\ \{(b_i, c_i)\}_i,\ \{s_j\}_j \big)$$

| Symbol | Definition |
|---|---|
| $S_t$ | `totalSupplyAssets(M, t)` — loan asset supplied |
| $B_t$ | `totalBorrowAssets(M, t)` — loan asset borrowed |
| $L_t = S_t - B_t$ | Instantaneous available liquidity |
| $U_t = B_t / S_t \in [0, 1]$ | Utilization rate |
| $C_t$ | `totalCollateralAssets(M, t)` — aggregate collateral pool |
| $P_t$ | Oracle-reported price of collateral in units of loan asset |
| $\{(b_i, c_i)\}_i$ | Borrower positions: borrowed amount, collateral amount |
| $\{s_j\}_j$ | Supplier positions |

### 1.2 Market constants (immutable per Morpho Blue design)

- $\text{LLTV} \in [0, 1]$ — liquidation LTV threshold
- $\text{IRM}: U \mapsto (r_{\text{borrow}}, r_{\text{supply}})$ — interest rate model
- Oracle source (Chainlink, Pyth, redstone, or composite)

### 1.3 Auxiliary functions

- $\pi(C, V)$ — DEX price impact for selling $V$ units of collateral $C$, calibrated empirically (§4)
- $\text{LTV}_i(t) = b_i / (c_i \cdot P_t)$ — per-position health
- Position $i$ is **liquidatable** at $t$ iff $\text{LTV}_i(t) > \text{LLTV}$

---

## 2. Stress Operator Framework

### 2.1 Definition

A stress scenario $\sigma$ is a quadruple:

$$\sigma = (\delta,\ T,\ h,\ \rho)$$

where:

- $\delta : \mathcal{X} \to \mathcal{X}$ — shock function applied to state at $t$
- $T$ — shock duration in blocks
- $h$ — observation horizon, $h \geq T$
- $\rho$ — behavioral / dynamic rule governing evolution from $t$ to $t+h$

The output of applying $\sigma$ to initial state $x(M, t)$ is a stress trajectory:

$$\mathcal{T}(M, \sigma) = \{x(M, t+k)\}_{k=0,\ldots,h}$$

from which we compute output metrics $\mathcal{M}(\sigma)$.

### 2.2 Two execution modes

For every scenario we define both:

- **Point mode (v0 baseline)**: $\delta$ is deterministic, calibrated to an empirical quantile of historical observations
- **Monte Carlo mode (v0 extension, retained)**: $\delta \sim F_\delta$ where $F_\delta$ is the empirical distribution; $N$ paths simulated; metrics reported as $(\text{mean}, p_5, p_{95}, p_{99})$

This dual structure means MC support is **architectural**, not bolted on. Any Phase 2 implementation that closes the door on MC violates the spec.

### 2.3 Behavioral regimes

- **Exogenous regime** (v0 baseline): liquidator selling does not move oracle price; only affects collateral recovery
- **Endogenous regime** (v0 extension): liquidator selling moves DEX price → if the market's oracle is DEX-derived (e.g., Uniswap TWAP), feedback activates

Selection of regime is **per-market**, driven by the oracle config. Markets using Chainlink with off-chain aggregation default to exogenous; markets using Uniswap TWAP default to endogenous.

---

## 3. Scenarios

### S1 — Withdrawal Run

**Description**: a fraction $\alpha$ of suppliers attempt to withdraw their balance over duration $T$.

**Shock $\delta_{S1}$**:

$$W_{\text{requested}}(\tau) = \alpha \cdot S_t \cdot w(\tau), \quad \tau \in [t, t+T]$$

where $w(\tau)$ is a withdrawal-arrival pattern (default: linear $w(\tau) = 1/T$; sensitivity test: front-loaded exponential).

**Calibration of $\alpha$**:

- Point mode: $\alpha = \text{quantile}_{0.99}\big(\sum_j \Delta s_j^- / S\big)$ over rolling 24h windows, per market, on the 12-month historical sample
- MC mode: $\alpha \sim F_\alpha^{\text{emp}}$, the empirical CDF of the same series

**Behavioral rule $\rho_{S1}$**:

A withdrawal request at block $\tau$ is honored iff $L_\tau \geq W_{\text{requested}}(\tau)$. Otherwise:

- The honored portion equals $\min(W_{\text{requested}}(\tau), L_\tau)$
- The unhonored portion accumulates in a `queued` register
- The supplier is recorded as **stuck** for accounting

Optional response: if `behavior = 'rate_response'`, IRM-driven rate spike triggers borrower repayment ($\propto$ rate gap × elasticity). Default at v0: no response (conservative).

**Pseudo-code**:

```python
def stress_S1(x0: State, alpha: float, T: int, h: int,
              arrival: str = "linear", behavior: str = "no_response") -> Trajectory:
    """Withdrawal run scenario."""
    schedule = generate_withdrawal_schedule(x0.S, alpha, T, arrival)  # array[h+1]
    traj = [x0]
    for k in range(1, h + 1):
        x = accrue_interest(traj[-1])  # IRM accrual
        due = schedule[k]
        honored = min(due, x.L)
        x.S -= honored
        x.queued += (due - honored)
        if behavior == "rate_response":
            x = apply_borrower_response(x)
        traj.append(x)
    return Trajectory(traj)
```

**Output metrics**:

- `time_to_illiquid` = $\min\{\tau : L_\tau = 0 \land \text{queued}_\tau > 0\}$, or $\infty$
- `total_queued(h)` — total unhonored withdrawals at horizon
- `stuck_ratio` = `total_queued(h) / (α · S_t)`

---

### S2 — Utilization Spike

**Description**: borrow demand spikes; new borrowers enter the market over $T$ blocks.

**Shock $\delta_{S2}$**:

$$\Delta B_{\text{requested}}(\tau) = \beta \cdot S_t \cdot w(\tau), \quad \tau \in [t, t+T]$$

with new borrowers entering at LTV = $\text{LLTV} - \epsilon$ (worst-case borrower behavior; tightens position health distribution).

**Calibration of $\beta$**:

- Point mode: $\beta = \text{quantile}_{0.99}(\Delta B^+ / S)$ over rolling 24h windows
- MC mode: $\beta \sim F_\beta^{\text{emp}}$

**Behavioral rule $\rho_{S2}$**:

- New borrows fill until $U = 1$; excess demand unsatisfied
- IRM raises $r_{\text{borrow}}$; supplier inflow modeled as $\Delta S^+ = \eta \cdot (r_{\text{borrow}} - r_{\text{benchmark}})^+$ if `behavior = 'rate_response'`, else null
- Position-level: new borrowers' LTV approaches LLTV, so a subsequent S3-style oracle move would liquidate them — **explicit linkage to S4**

**Output metrics**:

- `peak_utilization` = $\max_\tau U_\tau$
- `unsatisfied_borrow_demand`(h) — sum of unfilled requests
- `rate_trajectory` — full $r_{\text{borrow}}(\tau)$ path
- `induced_fragility` — fraction of new positions with $\text{LTV} > 0.95 \cdot \text{LLTV}$ (inputs to S4)

---

### S3 — Oracle Deviation

**Description**: collateral price drops by $\Delta$ over window $\Delta t$; oracle reports possibly lagged price.

**Shock $\delta_{S3}$**:

Two coupled price paths:

$$P^{\text{market}}_\tau = P_t \cdot \big(1 - \Delta \cdot g(\tau)\big), \quad \tau \in [t, t + \Delta t]$$
$$P^{\text{oracle}}_\tau = \text{TWAP}_\lambda\big(P^{\text{market}}_{\cdot}, \tau\big)$$

where $g(\tau)$ is a drawdown shape (linear by default, instant-step for shock test) and $\lambda$ is the oracle's smoothing window (read from contract config).

**Calibration**:

- $\Delta$ point mode: $\Delta = \text{quantile}_{0.99}(\text{drawdown over } \Delta t)$ from oracle/market history of the collateral asset
- $\Delta$ MC mode: $\Delta \sim F_\Delta^{\text{emp}}$ — fitted on rolling drawdown distribution
- Three values of $\Delta t$ in parallel: 1h, 24h, 7d
- $\lambda$ deterministic, read from oracle on-chain config

**Behavioral rule $\rho_{S3}$**:

At each block $\tau$:

1. Update per-position $\text{LTV}_i(\tau) = b_i / (c_i \cdot P^{\text{oracle}}_\tau)$
2. Identify $\mathcal{L}_\tau = \{i : \text{LTV}_i(\tau) > \text{LLTV}\}$
3. Liquidate positions in $\mathcal{L}_\tau$ with realistic latency $\delta_{\text{liq}}$ (default 2 blocks)
4. Recovery accounting per liquidation $i$:

$$R_i = c_i \cdot P^{\text{market}}_\tau \cdot (1 - \pi(C, c_i))$$
$$\text{shortfall}_i = \max(0, b_i - R_i)$$

Note: liquidation pricing uses **market price, not oracle price**, and slippage is computed via $\pi$.

**Pseudo-code**:

```python
def stress_S3(x0: State, drawdown: float, dt_blocks: int, h: int,
              oracle_lag: int, regime: str = "exogenous") -> Trajectory:
    """Oracle deviation scenario."""
    market_path = simulate_drawdown(x0.P, drawdown, dt_blocks, shape="linear")
    oracle_path = lag_smooth(market_path, oracle_lag)
    traj = [x0]
    for k in range(1, h + 1):
        x = accrue_interest(traj[-1])
        x.P_oracle = oracle_path[k]
        x.P_market = market_path[k]
        liquidatable = [p for p in x.positions if p.b / (p.c * x.P_oracle) > LLTV]
        for p in liquidatable:
            x = liquidate_position(x, p, slippage_fn=pi, regime=regime)
        traj.append(x)
    return Trajectory(traj)
```

**Output metrics**:

- `n_liquidated` — count of positions liquidated by horizon
- `bad_debt` = $\sum_i \text{shortfall}_i$
- `slippage_shortfall` — gap between oracle-priced and DEX-realized recovery: $\sum_i (c_i \cdot P^{\text{oracle}} - R_i)^+$

---

### S4 — Liquidation Cascade (composite)

**Description**: oracle drop + liquidations + DEX slippage feedback. Unlike S3, the endogenous regime here is the **default** (cascade is the point of the scenario).

**Shock $\delta_{S4}$**:

Joint shock $(\Delta, \Delta t)$ calibrated at p95 jointly (p99 jointly is unreliable on 12 months).

**Behavioral rule $\rho_{S4}$**:

Endogenous feedback — liquidator selling moves the DEX price; if oracle is DEX-derived, oracle follows. Update equation:

$$P^{\text{market}}_{\tau+1} = P^{\text{market}}_\tau \cdot \left(1 - \pi\big(C,\ V_{\text{liquidated}}(\tau)\big)\right)$$

If the oracle is `Uniswap_TWAP`-based:

$$P^{\text{oracle}}_{\tau+1} = \text{TWAP}_\lambda\big(P^{\text{market}}_{\cdot},\ \tau+1\big)$$

Else (Chainlink off-chain): no feedback, oracle path remains as in S3.

**Iteration order per block**:

```
1. Accrue interest
2. Update oracle price (with potential feedback from t-1)
3. Identify liquidatable positions
4. Execute liquidations (compute slippage on aggregate sold this block)
5. Update DEX price reflecting cumulative selling
6. (next block) → 1
```

This sequential structure prevents within-block circularity. A more sophisticated v1 model would solve a fixed-point per block.

**Pseudo-code**:

```python
def stress_S4(x0: State, drawdown: float, dt_blocks: int, h: int,
              oracle_config: OracleConfig,
              dex_curve: SlippageCurve) -> Trajectory:
    """Liquidation cascade scenario, endogenous by default."""
    market_path = simulate_drawdown(x0.P, drawdown, dt_blocks)
    traj = [x0]
    for k in range(1, h + 1):
        x = accrue_interest(traj[-1])
        x.P_market = market_path[k]
        x.P_oracle = oracle_apply(oracle_config, market_path, k)
        liquidatable = [p for p in x.positions
                        if p.b / (p.c * x.P_oracle) > LLTV]
        V_sold = sum(p.c for p in liquidatable)
        impact = dex_curve(x.collateral_asset, V_sold)
        for p in liquidatable:
            x = liquidate_position(x, p, slippage=impact, regime="endogenous")
        # propagate impact forward into market path
        if k < h:
            market_path[k+1:] = market_path[k+1:] * (1 - impact)
        traj.append(x)
    return Trajectory(traj)
```

**Output metrics**:

- `bad_debt_total` (point: scalar; MC: distribution)
- `cascade_depth` = $\max_\tau |\mathcal{L}_\tau|$ — max simultaneous liquidations
- `realized_slippage` — average and worst-block $\pi$ realized
- `feedback_amplification` = (endogenous cascade bad debt) / (exogenous-counterfactual bad debt) — measures the cost of feedback

---

### S5 — KelpDAO Replay (event-driven)

**Description**: counterfactual replay of the April 2026 KelpDAO event applied to the current Morpho Blue state.

**Shock $\delta_{S5}$**:

Reconstruct the historical price/event path from on-chain data (April 19–22, 2026). Apply this path as $P^{\text{market}}_\tau$ for the affected collateral types. For unaffected collaterals, no shock applied.

**Behavioral rule $\rho_{S5}$**: as in S4 (endogenous cascade), with the historical path replacing the synthetic drawdown.

**Output metrics**:

- Counterfactual `bad_debt` per market under the worst-event-of-2026 conditions
- Comparison ratio: `bad_debt_under_KelpDAO_replay / bad_debt_under_S4_p95`

This scenario is **the validation anchor** of the framework: a credible model should flag fragility in markets that, if they had existed identically in April 2026, would have suffered.

---

## 4. Calibration Plan

| Parameter | Source | Method | Notes |
|---|---|---|---|
| $\alpha$ (S1) | Subgraph `Withdraw` events | Empirical p99 over rolling 24h, per market | Min sample: 6 months for stable estimate |
| $\beta$ (S2) | Subgraph `Borrow` events | Empirical p99 over rolling 24h | Same min sample |
| $\Delta$ (S3, S4) | Oracle price feed | Empirical p99 negative log-return over $\Delta t$ | Per collateral; cross-check against CEX price |
| $\lambda$ (S3) | On-chain oracle config | Read directly | Chainlink heartbeat / TWAP window |
| $\pi(C, V)$ | DEX trades + 1inch quotes | Fit power-law $\pi = a \cdot V^b$, fallback to lookup | Validate fit per asset |
| KelpDAO path (S5) | On-chain April 19–22, 2026 | Direct extraction, no fitting | Anchor event |

**Statistical caveat (important)**: a 12-month window with rolling 24h gives ~365 disjoint or ~8,760 overlapping observations. p99 is estimated from ~3 (disjoint) or ~88 (overlapping) tail observations. **Confidence intervals on p99 are wide**, particularly for assets with limited history (sUSDe, cbBTC). This is an unavoidable v0 weakness — addressed via:

- Reporting bootstrap CIs on each calibrated quantile
- Using overlapping windows (with adjusted standard errors) where stationarity assumption is plausible
- Sensitivity tests at p95 and p99.5 alongside p99

---

## 5. Monte Carlo Mode (v0 retained extension)

### 5.1 Sampling

For each scenario, the MC mode samples shock parameters:

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

For each metric: $\text{mean}$, $\text{std}$, $p_5$, $p_{50}$, $p_{95}$, $p_{99}$.

### 5.3 Concrete MC use cases

1. **Bad debt distribution under S4**: $\mathbb{E}[\text{bad\_debt}]$, $p_{95}$, $p_{99}$. Headline number for a market's tail risk.
2. **Time-to-illiquid under S1**: median, IQR, $\Pr[\text{TTI} < 24\text{h}]$.
3. **Joint scenario VaR**: combine S3 + S1 (oracle drop + supplier panic) as compound event; estimate **99% liquidity VaR** = $p_{99}$ of net liquidity gap.

### 5.4 Computational budget

- One trajectory at $h = 30\,\text{d}$: ~216k blocks (Ethereum) → optimized to ~2,500 effective steps with sparse position updates → ~0.5–2 s in vectorized Python
- 10,000 MC paths × 5 markets × 5 scenarios = **250,000 trajectories**
- Single-machine estimate: 35–140 hours
- **Plan B**: 1,000 paths baseline (3.5–14 h) + 10,000 paths only on markets/scenarios flagged red. Recommended default for v0.
- Parallelization: `joblib` over CPUs gives 5–8× speedup on a workstation

### 5.5 Distributional assumption health-check

Empirical distributions on 12 months are **weak in the tail** — particularly for assets with short history. Mitigations:

- Block bootstrap with 24h block size to preserve autocorrelation
- Tail Pareto fit for $\Delta$ as sensitivity test
- Cross-asset pooling for $\pi$ where collateral types share liquidity venues

---

## 6. Validation Strategy

### 6.1 Backtest validation (KelpDAO ex-ante)

Apply the framework retrospectively at $t_0 = $ April 18, 2026 (one day before KelpDAO event). The framework **passes** if, for affected markets, at least one of:

- $\text{LCR}_{\text{onchain}}(M, t_0, \sigma_{S5}, h{=}24\text{h}) < 100\%$
- $\text{time\_to\_illiquid}(M, \sigma_{S1\,p99}, h{=}24\text{h}) < 24\text{h}$
- $\Pr[\text{bad\_debt} > 0 \mid \sigma_{S4}] > 5\%$

is satisfied **before** the event timestamp.

If the framework fails this test (no flag), one of three things is wrong: (a) framework is mis-calibrated, (b) event was unforeseeable from on-chain data alone, (c) spec has a bug. (b) is the academically interesting outcome; we report all three honestly.

### 6.2 Cross-check with public risk reports

For markets with Gauntlet / Chaos Labs / LlamaRisk public risk scores in the same window, compute Spearman rank correlation between our $\text{LCR}_{\text{onchain}}$ ranking and theirs. Expected: $\rho > 0.5$. Lower = either differentiation or model error; require explicit explanation in writeup.

### 6.3 Sanity tests (smoke)

- Markets with $U_{t_0} < 50\%$ and well-funded suppliers should NEVER reach illiquidity under $\sigma_{S1}$ at $\alpha = p_{99}$ → if they do, model bug
- Markets with collateral on Curve/Uniswap deep liquidity should have lower realized $\pi$ than markets with thin LRT/RWA collateral → if the ordering inverts, $\pi$-fit bug
- Framework should be **monotonic in stress severity**: more stress ⇒ worse metrics. Non-monotonicity = bug.

---

## 7. Output Schema (per market × scenario × horizon)

| Metric | Type | Format | Threshold |
|---|---|---|---|
| `LCR_onchain` | float | percentage | green ≥150 / yellow [100,150) / red <100 |
| `time_to_illiquid` | int | blocks (or `null`) | green ≥7d / yellow [24h,7d) / red <24h |
| `expected_bad_debt` | float | USD (point: scalar; MC: dist) | green 0 / yellow <1% TVL / red ≥1% |
| `slippage_shortfall` | float | USD | reported, no threshold |
| `cascade_depth` | int | count | reported, no threshold |
| `feedback_amplification` | float | ratio | reported, no threshold |
| `severity_flag` | enum | green/yellow/red | composite of above |

---

## 8. Implementation roadmap (forward references)

| Phase | Item | Dependency |
|---|---|---|
| 2 | Data acquisition (subgraph, RPC, DEX) | — |
| 2 | IRM, oracle, slippage models implemented | Phase 2 data |
| 3 | S1, S2, S3 standalone | Phase 2 |
| 3 | S4 cascade (both regimes) | S3 |
| 3 | S5 KelpDAO replay | S4 |
| 3 | MC mode for all scenarios | Point mode complete |
| 4 | Validation (§6) | All scenarios |
| 5 | Forward-looking application on top-5 markets | Phase 4 pass |

---

## 9. Document version control

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-04 | Initial Phase 1 deliverable |
