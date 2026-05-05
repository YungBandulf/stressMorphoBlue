# Methodology — Liquidity Stress Testing Framework for Morpho Blue

> Version: 0.2 (draft) — Last updated: May 2026
> Status: Phase 0 deliverable — pre-implementation methodological note
> Companion: [`SCENARIOS.md`](./SCENARIOS.md) — Phase 1 stress scenario specification
> Author: PA

---

## 1. Research Question

### 1.1 Primary hypothesis (falsifiable)

Given the on-chain state of a Morpho Blue market `M` at time `t` — characterized by the tuple `(totalSupplyAssets, totalBorrowAssets, LLTV, oracle, IRM, collateral DEX liquidity)` — there exists a stress scenario `σ` such that, at horizon `h`, the market enters one of two distress states:

- **Illiquid state**: incapacity to satisfy supplier withdrawal demand at `t + h` blocks, i.e. `requested_withdrawals(t, t+h) > available_liquidity(t+h)`.
- **Insolvent state**: realized bad debt `B(t+h) > 0`, i.e. liquidations failed to fully cover defaulted positions due to collateral price gap, oracle deviation, or liquidator slippage.

The probability of these states is bounded **empirically** from a 12-month rolling historical window, calibrated on observed stress events (notably the KelpDAO exploit of April 2026, USDC depeg of March 2023, and stETH discount of May 2022).

### 1.2 Secondary hypothesis (vault-curator angle)

For a MetaMorpho vault `V` with curator `c` at time `t`, define the **risk-discipline gap**:

```
Δ(V, t) = || X_observed(V, t) − X*(V, t) ||_2
```

where `X_observed` is the curator's actual allocation vector across approved Blue markets, and `X*` is the theoretical allocation that minimizes 30-day liquidity Value-at-Risk (VaR) under the stress framework defined in this document.

`Δ` is **the first quantitative measure of curator risk discipline** in DeFi to our knowledge — Gauntlet, Block Analitica and ChaosLabs publish absolute risk reports on individual markets but do not explicitly compute curator counterfactuals.

### 1.3 Why this matters

- **Academic gap**: Chiu et al. (BIS, 2023) show DeFi lending pools are inherently fragile, but published work focuses on monolithic pools (Aave, Compound). Morpho Blue's **isolated-market design** has no comparable formal stress-testing framework.
- **Industry gap**: Risk reports from Gauntlet, Block Analitica and LlamaRisk transpose Basel concepts informally. We provide **explicit Basel III mapping** with stated limitations.
- **Timing**: The KelpDAO event (April 2026) generated ~196M USD in bad debt on Aave and ~8B USD of capital migration to Morpho. This is the largest stress event of the cycle and provides a calibration anchor that did not exist before.

---

## 2. Theoretical Framework

### 2.1 Basel III LCR mapping

The Liquidity Coverage Ratio (LCR), defined in BCBS 238 (2013):

```
LCR = HQLA / Net_Cash_Outflows_30d ≥ 100%
```

We construct an on-chain analogue `LCR_onchain(M, t, σ, h)` for a Morpho Blue market `M`:

```
                      L₁(M,t) + 0.85 · L_{2A}(M,t,σ) + 0.50 · L_{2B}(M,t,σ)
LCR_onchain = ─────────────────────────────────────────────────────────────
                        O_σ(M,t,h) − min(I_σ(M,t,h), 0.75 · O_σ)
```

| Basel component | Basel definition | Morpho Blue analogue |
|---|---|---|
| **HQLA Level 1** (haircut 0%) | Cash, central bank reserves, top sovereign debt | Instant liquidity: `totalSupplyAssets(M,t) − totalBorrowAssets(M,t)` |
| **HQLA Level 2A** (haircut 15%) | Highly-liquid corporate / covered bonds | Collateral liquidatable on DEX at oracle price, discounted by **median DEX slippage** for typical liquidation size |
| **HQLA Level 2B** (haircut 25-50%) | Lower-rated corporate, equities | Collateral with limited DEX liquidity (exotic LRTs, RWA tokens), discounted by **p99 DEX slippage** |
| **Outflows: stable retail** (5%) | Insured retail deposits | Proxy: median historical withdrawal velocity |
| **Outflows: less-stable retail** (10%) | Non-insured retail deposits | Proxy: p90 historical withdrawal velocity |
| **Outflows: wholesale unsecured** (40-100%) | Non-financial / financial corp | **Whale concentration**: simultaneous withdrawal by top-5 suppliers under stress |
| **Inflows: secured lending** (cap 75%) | Repayments, collateral inflows | Forced repayments through liquidations during the stress window |

### 2.2 Honest critique of the LCR mapping

The mapping is non-trivial and several choices are **defensible but not unique**. We list the tensions explicitly:

1. **Haircut calibration is arbitrary at v0**: the 0.85 / 0.50 coefficients borrowed from Basel are calibrated on macro-prudential data unrelated to crypto. **v1 will replace these constants with empirical haircuts** estimated from realized DEX slippage on liquidation events of comparable size.
2. **Time-unit mismatch**: Basel reasons in months; on-chain we measure in blocks (12s on Ethereum, 2s on Base). The `h = 30 days` Basel parameter is not natural; we expose `h` as a free parameter and report results at three horizons: 24h, 7d, 30d.
3. **No equivalent of "stable funding"**: in DeFi all suppliers are 100% callable by construction. The Basel concept of "operational deposits" has no on-chain analogue — we therefore expect that **all DeFi lending pools have a structurally low LCR by Basel standards**, and the LCR is most informative *relative to itself across markets and time*, not in absolute terms.
4. **Oracle as exogenous**: we treat oracle prices as exogenous inputs. In reality, oracle behavior (TWAP smoothing, deviation thresholds, fallback logic) is endogenous to the stress scenario. This is a deliberate v0 simplification — modeled as a sensitivity analysis, not a structural feature.

### 2.3 NSFR — the more interesting angle

The Net Stable Funding Ratio (BCBS 295, 2014):

```
NSFR = ASF / RSF ≥ 100%
```

For DeFi lending, a brute-force application yields:

- **ASF weight**: suppliers are instantly callable → ASF factor ≈ 0%
- **RSF weight**: borrows have no contractual maturity (perpetual) → RSF factor ≈ 100%

⇒ **NSFR_brute ≈ 0** for any DeFi lending pool. This is a **structural insight rarely articulated in DeFi risk literature**, because crypto-native analysts typically do not work in the Basel framework.

The interesting analysis is the **conditional NSFR**: how much funding is *empirically* stable, given oracle health, prevailing yield differential vs alternatives, and supplier concentration? This reduces to estimating a **withdrawal-survival function** `S(t | features)`, which we model via Kaplan-Meier-style empirical CDFs on historical supplier behavior.

This is **the academic contribution of the project** beyond the descriptive stress-test layer.

---

## 3. Scope

### 3.1 Markets

Top-5 Morpho Blue markets by TVL on Ethereum mainnet at the start of Phase 1 (to be frozen on day 1 of data acquisition; see [`scripts/select_markets.py`](../scripts/select_markets.py) once implemented).

**Candidate set (subject to revalidation)**:
- `wstETH / WETH`
- `wstETH / USDC`
- `WBTC / USDC`
- `cbBTC / USDC`
- `sUSDe / USDC`

Selection criteria, in order: (i) TVL > 100M USD, (ii) age > 6 months on chain, (iii) at least one stress event observable in the window.

### 3.2 Historical window

12 rolling months: **May 2025 → May 2026**. This window contains:

- KelpDAO exploit and ensuing TVL migration (April 2026) — **calibration anchor**
- Sundry oracle deviations and minor depegs (continuous)
- General macro stress around Q3 2025 (to verify at data acquisition)

### 3.3 Stress horizons

Three values of `h`, reported in parallel:

- **24 hours** — equivalent of an intraday liquidity squeeze
- **7 days** — short-horizon stress
- **30 days** — Basel-equivalent horizon

### 3.4 Stress scenarios (4 + 1)

| # | Scenario | Description | Severity |
|---|---|---|---|
| **S1** | **Withdrawal run** | Suppliers withdraw `X%` of `totalSupply` over `T` blocks | `X = p99` empirical, `T ∈ {1h, 24h, 7d}` |
| **S2** | **Utilization spike** | Sudden borrow demand pushes utilization → 100% | Spike calibrated on top-3 historical events |
| **S3** | **Oracle deviation** | Collateral price drops by `Δ%` in `Δt`; oracle reports lagged price | `Δ = p99` historical drawdown of asset over `Δt` |
| **S4** | **Liquidation cascade** | Combination: oracle drop + liquidations + DEX slippage feedback | All three at p95 jointly |
| **S5** | **KelpDAO replay** | Backtest of April 2026 event applied to Morpho markets ex-post | Empirical, no parameter |

### 3.5 Output metrics

For each `(market M, scenario σ, horizon h)` tuple:

- `LCR_onchain(M, t, σ, h)` — primary metric, reported as time series and worst-case
- `Time-to-illiquid(M, σ)` — first block at which `available_liquidity < pending_withdrawals`
- `Expected_bad_debt(M, σ, h)` — sum of unrecovered debt at end of horizon
- `Slippage-adjusted_shortfall(M, σ, h)` — gap between oracle-priced collateral and DEX-realized recovery
- `Withdrawal_survival_curve` — empirical `S(t | σ)` for hypothesis 2

---

## 4. Limitations (explicit, exhaustive)

1. **Endogeneity ignored at v0**: prices, withdrawals, and liquidations are treated as separable processes. In reality, large liquidations move DEX prices, which trigger more liquidations (a feedback loop). Capponi & Jia (2021) and follow-up work formalize this. Modeling it requires agent-based simulation or a fixed-point solver — **out of scope for v0**, flagged for v1.
2. **Oracle as exogenous input**: TWAP behavior, fallback paths, and oracle outages are not endogenously modeled. Sensitivity analysis only.
3. **MEV and liquidator competition**: assumed perfect liquidation (no liquidator stuck in mempool, no priority gas auction failure). This biases bad-debt estimates **downward** under v0.
4. **Cross-market contagion**: by Morpho Blue design, markets are isolated → no cross-market contagion at the protocol layer. **However**, MetaMorpho vaults link markets economically through curator allocation. Vault-level analysis (hypothesis 2) introduces this dimension.
5. **Calibration on a short window**: 12 months of data on a fast-evolving protocol means small-sample bias. Confidence intervals will be reported but should be taken as indicative.
6. **Monte Carlo as v0 retained extension**: scenarios are designed in dual mode — point (deterministic shocks at empirical quantiles) and Monte Carlo (sampled from empirical distributions, with $N$ paths and confidence intervals). MC is **not** a future concern: it is part of the v0 spec (see [`SCENARIOS.md §5`](./SCENARIOS.md)). The honest caveat is statistical: a 12-month sample produces wide confidence intervals on tail quantiles ($p_{99}$ estimated from ~3 disjoint or ~88 overlapping observations). Block bootstrap and Pareto-tail sensitivity tests are used to bound this uncertainty, but tail estimation on short DeFi history remains the dominant source of model risk.
7. **Solidity behavior not simulated end-to-end**: we model the economic state, not gas / mempool dynamics. A Foundry-fork backtest would close this gap (v1).
8. **Smart contract risk excluded**: the framework assumes Morpho Blue contracts execute correctly. Contract-level risk (bugs, governance attacks) is out of scope.

---

## 5. References

See [`references.md`](./references.md) for the full bibliography. Core anchors:

- **Basel framework**: BCBS 238 (LCR, 2013), BCBS 295 (NSFR, 2014)
- **DeFi lending theory**: Gudgeon, Werner, Perez & Knottenbelt (2020) ; Capponi & Jia (2021, 2023) ; Chiu, Ozdenoren, Yuan & Zhang (BIS WP 1062, 2023)
- **Protocol specification**: Morpho Labs — Morpho Blue Whitepaper and Yellow Paper
- **Industry benchmarks**: Steakhouse Financial public Maker analyses ; Block Analitica risk reports ; LlamaRisk Aave / Curve reports

---

## 6. Document version control

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-04 | Initial draft (Phase 0) |
| 0.2 | 2026-05-04 | §4.6 — Monte Carlo retained as v0 extension; companion `SCENARIOS.md` published |
