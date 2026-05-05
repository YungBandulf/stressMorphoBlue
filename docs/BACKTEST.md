# Backtest Framework — Phase 4

> Version: 0.2 — Last updated: May 2026
> Status: Phase 4 deliverable — historical-event validation framework
> Companion documents: [`SCENARIOS.md §6.1`](./SCENARIOS.md) — validation criteria;
> [`GLOSSARY.md`](./GLOSSARY.md) — definitions of all specialised terms.

---

## A note on terminology

This document defines every specialised term either at first use or in
[`GLOSSARY.md`](./GLOSSARY.md). Mathematical symbols are introduced
with their units. Abbreviations are spelled out on first use, with the
abbreviation in parentheses, and used as the abbreviation thereafter
within the same section.

---

## 1. Objective

Validate the stress framework against real historical events. The
pass-or-fail criterion from [`SCENARIOS.md §6.1`](./SCENARIOS.md) is
precise: applied at $t_0$ = one day before the event, the framework
must flag at least one of:

- *On-chain Liquidity Coverage Ratio*: $\mathrm{LCR}_{\text{on-chain}}(M, t_0, \sigma_{\text{S5}}, h = 24\text{h}) < 100\%$;
- *Time-to-illiquid*: $\mathrm{time\text{-}to\text{-}illiquid}(M, \sigma_{\text{S1, 99th-percentile}}, h = 24\text{h}) < 24$ hours;
- *Bad-debt probability*: $\Pr[\text{bad debt} > 0 \mid \sigma_{\text{S4}}] > 5\%$.

If the framework fails this test, we report honestly. There are three
possible explanations:

1. **Calibration error**: the framework is correctly designed but
   miscalibrated. Adjustable in a later version.
2. **Inherent unforeseeability**: the event was not predictable from
   on-chain data alone (for example, an off-chain exploit signal).
   This is the *academically interesting* outcome.
3. **Specification bug**: the framework as specified does not capture
   the relevant risk channel. Requires methodology revision.

We commit to reporting all three cases honestly in the public writeup
(see [`REPORT.md`](./REPORT.md)).

---

## 2. Events selected for validation

We use three high-impact events with distinct risk profiles, spanning
the 2022 to 2026 window. Each event is packaged as a versioned
*fixture* under `data/fixtures/<event-id>/`, comprising:

- `event.yaml` — event metadata (date, $t_0$, affected markets,
  summary);
- `prices.csv` — collateral price time series (oracle and market) for
  $\pm 5$ days around the event;
- `markets.json` — affected market states at $t_0 - 1$ day (snapshot);
- `positions.csv` — borrower positions on those markets at $t_0 - 1$
  day;
- `dex_slippage.csv` — Uniswap V3 historical swaps for slippage
  calibration;
- `sources.md` — full source attribution per data point.

### 2.1 KelpDAO collateral exploit (April 2026) — primary anchor

- **Date**: 20 April 2026, approximately 14:00 UTC.
- **Day-zero ($t_0$)**: 19 April 2026, 23:59 UTC.
- **Description**: The KelpDAO liquid-restaking-token collateral was
  exploited, draining approximately 292 million U.S. dollars from
  Aave; approximately 196 million U.S. dollars materialised as bad
  debt. Morpho Blue isolated lending markets using the same collateral
  (rsETH and ezETH variants) saw cascading liquidations.
- **Why anchor**: most recent, highest-impact, *isolated-market design
  under test*, large MetaMorpho vault flows post-event.

### 2.2 USDC depeg (March 2023) — stable-collateral stress

- **Date**: 11 March 2023, approximately 02:00 UTC.
- **Day-zero ($t_0$)**: 10 March 2023, 02:00 UTC.
- **Description**: The collapse of Silicon Valley Bank — Circle, the
  USDC issuer, held approximately 3.3 billion U.S. dollars at Silicon
  Valley Bank — caused USDC to trade briefly at approximately 0.88
  U.S. dollars on secondary markets. The Aave USDC market saw mass
  migration; many DAI-collateralised positions liquidated as DAI fell
  in tandem with USDC, given DAI's significant USDC backing on Maker.
- **Why selected**: stable-on-stable depeg; oracle-versus-market gap
  pattern; predates Morpho Blue. We use this event as a
  *transposition test*: we apply the framework to a *counterfactual*
  Morpho Blue lending market with the same collateral-and-loan-asset
  pair.

### 2.3 Staked-Ether discount (May 2022) — liquid-staking-token discount

- **Date**: 12 May 2022, approximately 09:00 UTC.
- **Day-zero ($t_0$)**: 11 May 2022, 09:00 UTC.
- **Description**: Staked-Ether traded at approximately 0.94 of its
  underlying asset, Ether, on Curve following the collapse of Terra
  and its UST stablecoin, combined with concerns over the staked-Ether
  withdrawal queue (pre-Shapella, staked-Ether had no direct
  withdrawal mechanism — the Curve staked-Ether-to-Ether pool was the
  de facto exit liquidity, and it became heavily skewed). Aave
  staked-Ether-to-Ether positions sat near liquidation thresholds;
  manual intervention from the Aave team avoided large liquidation
  cascades.
- **Why selected**: a structural discount on a liquid-staking-token
  versus its underlying asset; a slow-rolling drawdown (not instant);
  predates Morpho Blue — counterfactual application.

---

## 3. Counterfactual methodology

For events that predate Morpho Blue (USDC, staked-Ether), we cannot
directly observe Morpho Blue lending-market state. Instead, we
*construct counterfactual markets* with parameters reflective of
current Morpho Blue practice:

- The liquidation loan-to-value threshold $\Lambda$ is chosen by
  analogy with similar live markets today (for example, the USDC-USDC0
  Morpho Blue market $\Lambda$ is used for the USDC depeg fixture);
- The interest rate model is the AdaptiveCurveIRM with default
  parameters;
- The position distribution is sampled from a synthetic but realistic
  distribution (50 to 200 positions, log-normal sizes, loan-to-value
  drawn from a Beta distribution centred near 0.7).

This is **not a true backtest of historical Morpho Blue performance**.
It is a "what-if" stress: had Morpho Blue existed with realistic
parameters at the time of the event, would our framework have flagged
it?

The KelpDAO event predates the framework but post-dates Morpho Blue,
so for that event we use the *observed Morpho Blue lending-market
state* at $t_0 - 1$. This is the strongest validation; the other two
are weaker counterfactuals.

We report all three transparently and weight the conclusions
accordingly.

---

## 4. Fixture format

### 4.1 `event.yaml`

```yaml
event_id: "kelpdao_2026_04"
event_name: "KelpDAO liquid-restaking-token exploit"
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

| ts | symbol | `price_usd` | source |
|---|---|---|---|
| 2026-04-15T00:00:00Z | rsETH | 3142.50 | chainlink (block 21923500) |
| ... | ... | ... | ... |

Sampled at hourly cadence within the window. Source attribution per
row.

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

The `lltv` field denotes the liquidation loan-to-value threshold,
abbreviated `LLTV` in the on-chain Solidity code by Morpho Labs and
preserved here for compatibility.

### 4.4 `dex_slippage.csv`

Historical Uniswap V3 swaps for the affected collateral. Used to
calibrate the slippage curve $\pi(C, V)$ at the time of the event
(not today's liquidity).

| `swap_ts` | `collateral_symbol` | `volume_native` | `volume_usd` | `oracle_price` | `realized_price` | `slippage_bps` | source |
|---|---|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... | ... | `uniswap_v3:0xabc...` |

Slippage in `slippage_bps` is in basis points (1 basis point = 0.01%).

---

## 5. Validation criteria — pass-or-fail rules

For each event, the framework runs and produces a verdict.

```python
@dataclass
class BacktestVerdict:
    event_id: str
    affected_markets: list[str]
    framework_flagged: bool       # True if any criterion was triggered
    triggered_criteria: list[str]  # which of the 3 §6.1 criteria fired
    metrics: dict[str, float]      # values of LCR, TTI, P[bad_debt > 0]
    pass_fail: str                 # "PASS" if framework_flagged matches expected_red_flag
```

**Aggregate success metric**: at least 2 of 3 events must pass. The
KelpDAO event must pass absolutely (it is the primary anchor).

**Severity flags** (from [`SCENARIOS.md §7`](./SCENARIOS.md)):

- **Red**: at least one criterion is triggered with margin
  ($\mathrm{LCR}_{\text{on-chain}} < 80\%$, time-to-illiquid $< 12$
  hours, or $\Pr[\text{bad debt} > 0] > 20\%$);
- **Yellow**: criterion is triggered weakly
  ($\mathrm{LCR}_{\text{on-chain}} \in [80\%, 100\%)$, time-to-illiquid
  $\in [12\text{h}, 24\text{h})$, or $\Pr[\text{bad debt} > 0] \in [5\%, 20\%)$);
- **Green**: no criterion is triggered.

---

## 6. Limitations of this backtest

1. **Counterfactual weakness**: the USDC and staked-Ether events
   predate Morpho Blue. The results are indicative, not historically
   accurate.
2. **Position distribution is synthetic** for counterfactual events.
   Real borrower behaviour (concentration, leverage skew) is hard to
   reconstruct.
3. **Slippage curves are calibrated on time-of-event Uniswap data**.
   Liquidity conditions evolved post-event; we use what would have
   been observable to a liquidator at $t_0$.
4. **No maximal-extractable-value or liquidator-competition
   modelling**. Bias: bad debt is underestimated.
5. **Three events is a small sample**. We report results, not
   statistical significance. A future extension would extend to 10 or
   more events.

---

## 7. Document version control

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-04 | Initial Phase 4 specification |
| 0.2 | 2026-05-05 | All abbreviations spelled out at first use; companion `GLOSSARY.md` published |
