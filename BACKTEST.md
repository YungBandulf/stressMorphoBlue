# Backtest Framework — Phase 4

> Version: 0.1 — Last updated: May 2026
> Status: Phase 4 deliverable — historical backtest framework
> Companion: [`SCENARIOS.md §6.1`](./SCENARIOS.md) — validation criteria

---

## 1. Objective

Validate the stress framework against real historical events. The pass/fail
criterion from `SCENARIOS.md §6.1` is precise: applied at $t_0$ = one day
before the event, the framework must flag at least one of:

- $\text{LCR}_{\text{onchain}}(M, t_0, \sigma_{S5}, h{=}24\text{h}) < 100\%$
- $\text{time\_to\_illiquid}(M, \sigma_{S1, p_{99}}, h{=}24\text{h}) < 24\text{h}$
- $\Pr[\text{bad\_debt} > 0 \mid \sigma_{S4}] > 5\%$

If the framework fails the test, we report honestly. There are three possible
explanations:

1. **Calibration error**: the framework is correctly designed but
   miscalibrated. Adjustable in v1.
2. **Inherent unforeseeability**: the event was not predictable from on-chain
   data alone (e.g., an off-chain exploit signal). This is the *academically
   interesting* outcome.
3. **Specification bug**: the framework as specified does not capture the
   relevant risk channel. Requires methodology revision.

We commit to reporting all three cases honestly in the public writeup.

---

## 2. Events Selected for Validation

We use three high-impact events with distinct risk profiles, spanning the
2022–2026 window. Each event is packaged as a versioned **fixture** under
`data/fixtures/<event>/`, comprising:

- `event.yaml` — event metadata (date, T0, affected markets, summary)
- `prices.csv` — collateral price time series (oracle + market) ± 5 days
- `markets.json` — affected market states at T-1 day (snapshot)
- `positions.csv` — borrower positions on those markets at T-1 day
- `dex_slippage.csv` — Uniswap V3 historical swaps for slippage calibration
- `sources.md` — full source attribution per data point

### 2.1 KelpDAO exploit (April 2026) — primary anchor

- **Date**: 20 April 2026, ~14:00 UTC
- **T0**: 19 April 2026, 23:59 UTC
- **Description**: KelpDAO LRT collateral exploit drained ~$292M from Aave;
  ~$196M materialized as bad debt. Morpho Blue isolated markets using the
  same collateral (rsETH, ezETH variants) saw cascading liquidations.
- **Why anchor**: most recent, highest-impact, isolated-market design under
  test, large MetaMorpho vault flows post-event.

### 2.2 USDC depeg (March 2023) — stable collateral stress

- **Date**: 11 March 2023, 02:00 UTC
- **T0**: 10 March 2023, 02:00 UTC
- **Description**: SVB collapse → Circle had $3.3B at SVB → USDC briefly
  traded ~$0.88 on secondary markets. Aave USDC market saw mass migration;
  many DAI markets liquidated as DAI fell with USDC collateral on Maker.
- **Why selected**: stable-on-stable depeg, oracle vs market gap pattern,
  pre-Morpho-Blue (predates protocol) — used as a *transposition test*: we
  apply the framework to a **counterfactual** Morpho Blue market with the
  same collateral/loan pair.

### 2.3 stETH discount (May 2022) — LST collateral discount

- **Date**: 12 May 2022, 09:00 UTC
- **T0**: 11 May 2022, 09:00 UTC
- **Description**: stETH traded at ~0.94 of ETH on Curve following Terra/UST
  collapse + concerns over Lido withdrawal queue. Aave stETH/ETH positions
  near liquidation thresholds; manual intervention from Aave team.
- **Why selected**: structural discount on LST vs underlying, slow-rolling
  drawdown (not instant), predates Morpho Blue — counterfactual application.

---

## 3. Counterfactual Methodology

For events that predate Morpho Blue (USDC, stETH), we cannot directly observe
Morpho Blue market state. Instead, we **construct counterfactual markets**
with parameters reflective of current Morpho Blue practice:

- LLTV chosen by analogy with similar live markets today (e.g., USDC/USDC0
  Morpho market → LLTV used for USDC depeg fixture)
- IRM = AdaptiveCurveIRM with default parameters
- Position distribution sampled from a synthetic but realistic distribution
  (50–200 positions, log-normal sizes, LTV ~ Beta around 0.7)

This is **not a true backtest of historical Morpho Blue performance**. It is
a "what-if" stress: had Morpho Blue existed with realistic parameters at the
time of the event, would our framework have flagged it?

The KelpDAO event predates the framework but post-dates Morpho Blue, so for
that event we use **observed Morpho Blue market state at T-1**. This is the
strongest validation; the other two are weaker counterfactuals.

We report all three transparently and weight conclusions accordingly.

---

## 4. Fixture Format

### 4.1 `event.yaml`

```yaml
event_id: "kelpdao_2026_04"
event_name: "KelpDAO LRT exploit"
event_ts: "2026-04-20T14:00:00Z"
t0_ts: "2026-04-19T23:59:00Z"
window_pre_days: 5
window_post_days: 5
affected_collaterals: ["rsETH", "ezETH"]
affected_loan_assets: ["WETH", "USDC"]
counterfactual: false  # KelpDAO is post-Morpho-Blue
expected_red_flag: true  # framework must flag
notes: |
    Event details, post-mortem links, sources.
```

### 4.2 `prices.csv`

| ts | symbol | price_usd | source |
|---|---|---|---|
| 2026-04-15T00:00:00Z | rsETH | 3142.50 | chainlink (block 21923500) |
| ... | ... | ... | ... |

Sampled at hourly cadence within the window. Source attribution per row.

### 4.3 `markets.json`

```json
{
  "market_id": "0x...",
  "loan_asset_symbol": "USDC",
  "collateral_asset_symbol": "rsETH",
  "lltv": 0.86,
  "snapshot_block": 21924000,
  "snapshot_ts": "2026-04-19T23:59:00Z",
  "total_supply_assets": 45000000,
  "total_borrow_assets": 38000000,
  "total_collateral": 12500.0,
  "oracle_price_at_snapshot": 3050.0,
  "rate_at_target_at_snapshot": 0.045
}
```

### 4.4 `dex_slippage.csv`

Historical Uniswap V3 swaps for the affected collateral. Used to calibrate
the slippage curve $\pi(C, V)$ at the time of the event (not today's
liquidity).

| swap_ts | collateral_symbol | volume_native | volume_usd | oracle_price | realized_price | slippage_bps | source |
|---|---|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... | ... | uniswap_v3:0xabc... |

---

## 5. Validation Criteria — Pass/Fail Rules

For each event, the framework runs and produces a verdict:

```python
@dataclass
class BacktestVerdict:
    event_id: str
    affected_markets: list[str]
    framework_flagged: bool       # True if any criterion below was triggered
    triggered_criteria: list[str]  # which of the 3 §6.1 criteria fired
    metrics: dict[str, float]      # values of LCR, TTI, P[bad_debt > 0]
    pass_fail: str                 # "PASS" if framework_flagged matches expected_red_flag
```

**Success metric across all events**: ≥ 2 of 3 must pass. KelpDAO must pass
absolutely (it is the primary anchor).

**Severity flags** (from `SCENARIOS.md §7`):
- `red`: at least one criterion triggered with margin (LCR < 80%, TTI < 12h,
  P[bad_debt>0] > 20%)
- `yellow`: criterion triggered weakly (LCR ∈ [80%, 100%), TTI ∈ [12h, 24h),
  P[bad_debt>0] ∈ [5%, 20%])
- `green`: no criterion triggered

---

## 6. Limitations of This Backtest

1. **Counterfactual weakness**: USDC and stETH events predate Morpho Blue.
   Results are indicative, not historically accurate.
2. **Position distribution is synthetic** for counterfactual events. Real
   borrower behavior (concentration, leverage skew) is hard to reconstruct.
3. **Slippage curves are calibrated on time-of-event Uniswap data**. Liquidity
   conditions evolved post-event; we use what would have been observable to
   a liquidator at T0.
4. **No MEV / liquidator competition modeling**. Bias: bad debt is
   underestimated.
5. **Three events is a small sample**. We report results, not statistical
   significance. v1 extension: extend to 10+ events.

---

## 7. Document version control

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-04 | Initial Phase 4 spec |
