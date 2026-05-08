# Data Architecture: Phase 2

> Version: 0.2. Last updated: May 2026
> Status: Phase 2 deliverable. data-acquisition specification and implementation
> Companion document: [`GLOSSARY.md`](./GLOSSARY.md). definitions of all specialised terms.
> Scope: top-three lending markets initially, extension to top-five at Phase 2 close.

---

## A note on terminology

This document defines every specialised term either at first use or in
[`GLOSSARY.md`](./GLOSSARY.md). Mathematical symbols are introduced
with their units. Abbreviations are spelled out on first use, with the
abbreviation in parentheses, and used as the abbreviation thereafter
within the same section.

---

## 1. Source-of-truth map

Each data category has **exactly one canonical source**. Cross-source
validation is performed but never triggers data fusion at the storage
layer.

| Category | Canonical source | Why | Validation source |
|---|---|---|---|
| Market state (total supply, total borrow, supply-and-borrow shares, accruals) | Remote Procedure Call (the protocol used to communicate with a blockchain node from off-chain software, abbreviated *RPC* hereafter), specifically `eth_call` on the Morpho Blue contract at specific block heights | Exact, deterministic, safe from chain reorganisation at depth $\geq 32$ blocks | Subgraph (which has higher latency and reorganisation risk) |
| Events (Supply, Withdraw, Borrow, Repay, Liquidate) | Subgraph (Morpho hosted on The Graph protocol) | Native event indexing | RPC `eth_getLogs` for spot validation |
| Oracle prices (per market oracle configuration) | RPC `latestRoundData` for Chainlink, equivalent calls for Pyth and Redstone | Same oracle the contract reads | Off-chain centralised-exchange feed (Binance, Coinbase) |
| Decentralised-exchange liquidity and realised slippage | 1inch quote application programming interface (forward-looking) and Uniswap V3 historical swaps via subgraph (backward-looking) | Forward-looking quotes feed scenarios; historical fills feed calibration | Cross-check via CoW Swap fills |
| Aggregate Total Value Locked and market metadata | DeFiLlama application programming interface | Single endpoint, cached | DeFiLlama webpage |
| Liquidation history (executed) | Subgraph `Liquidate` events | Native | RPC `eth_getLogs` |
| MetaMorpho vault allocations | RPC `MetaMorpho.config()` and balance queries | Exact | Subgraph |

**Rule**: when the modelling code reads `liquidations`, it reads from
`data/parquet/liquidations.parquet`, never directly from a vendor.
The data layer is the application programming interface.

---

## 2. Storage layout

```
data/
├── raw/                          # Immutable raw dumps (never edited, gitignored)
│   ├── dune/                     # CSV exports from Dune queries
│   ├── subgraph/                 # GraphQL response JSON (gzipped)
│   ├── rpc/                      # Block-state RPC responses (JSON-LD)
│   ├── oracle/                   # Per-block oracle reads
│   └── dex/                      # 1inch quotes plus Uniswap swaps
├── cache/                        # Derived Parquet files (regeneratable, gitignored)
│   ├── markets.parquet           # Market metadata (immutable Morpho Blue parameters)
│   ├── market_state.parquet      # Time series of (S, B, U) per market per block sample
│   ├── events_supply.parquet
│   ├── events_withdraw.parquet
│   ├── events_borrow.parquet
│   ├── events_repay.parquet
│   ├── events_liquidate.parquet
│   ├── positions.parquet         # Reconstructed positions per (market, borrower)
│   ├── oracle_prices.parquet     # Per-market oracle price time series
│   ├── dex_slippage.parquet      # Calibration data for the slippage curve
│   └── tvl_daily.parquet         # DeFiLlama Total Value Locked history
├── catalog.duckdb                # DuckDB views over Parquet for SQL access
└── .gitkeep
```

---

## 3. Schema specifications

All Parquet files use **strict typed schemas** built with PyArrow.
Type drift produces a test failure.

### 3.1 `markets.parquet`

Immutable Morpho Blue market parameters (one row per market;
approximately a few hundred rows total).

| Column | Type | Description |
|---|---|---|
| `market_id` | string | Morpho Blue market identifier (32-byte hash, hex-encoded with `0x`) |
| `loan_asset` | string | Loan asset address, lowercase hex |
| `loan_asset_symbol` | string | Symbol (USDC, WETH, etc.) |
| `loan_asset_decimals` | int8 | Decimals of the loan asset |
| `collateral_asset` | string | Collateral asset address |
| `collateral_asset_symbol` | string | Symbol |
| `collateral_asset_decimals` | int8 | Decimals |
| `oracle` | string | Oracle contract address |
| `oracle_type` | string | Categorical: `chainlink`, `pyth`, `redstone`, `uniswap_twap`, `composite` |
| `irm` | string | Address of the interest rate model contract |
| `lltv` | float64 | Liquidation loan-to-value threshold (0 to 1) |
| `created_at_block` | uint64 | Block of the `CreateMarket` event |
| `created_at_ts` | timestamp\[ns, tz=UTC\] | Wall-clock time |

### 3.2 `market_state.parquet`

Time series of market state. Sampled at **6-hour cadence** by default;
denser sampling around stress events.

| Column | Type | Description |
|---|---|---|
| `market_id` | string | Foreign key into `markets.market_id` |
| `block_number` | uint64 | Ethereum block |
| `block_ts` | timestamp\[ns, tz=UTC\] | Wall-clock time |
| `total_supply_assets` | float64 | Loan asset supplied (loan-asset native units, decimals applied) |
| `total_supply_shares` | float64 | Total supply shares |
| `total_borrow_assets` | float64 | Loan asset borrowed |
| `total_borrow_shares` | float64 | Total borrow shares |
| `total_collateral` | float64 | Collateral pool (collateral-asset units) |
| `last_update` | uint64 | Contract `lastUpdate` field (block) |
| `fee` | float64 | Market fee (0 to 1) |

Constraints (validated):
- `total_borrow_assets <= total_supply_assets` (cannot over-borrow);
- `block_ts` strictly increasing per market;
- No NaN values in mandatory columns.

### 3.3 Event schemas

The five event tables (`events_supply.parquet`,
`events_withdraw.parquet`, `events_borrow.parquet`,
`events_repay.parquet`, `events_liquidate.parquet`) share a common base
schema and add event-specific columns.

| Column | Type | Description |
|---|---|---|
| `market_id` | string | Foreign key |
| `block_number` | uint64 | |
| `block_ts` | timestamp\[ns, tz=UTC\] | |
| `tx_hash` | string | |
| `log_index` | uint32 | For exact event ordering within a transaction |
| Event-specific columns | (varies) | See `src/morpho_stress/data/schemas.py` |

The `events_liquidate.parquet` table is the highest-stakes event for
the framework. Its columns include `repaid_assets`, `repaid_shares`,
`seized_assets`, `bad_debt_assets`, `bad_debt_shares`, all denominated
in loan or collateral asset units as appropriate.

### 3.4 `positions.parquet`

Reconstructed per-(market, borrower) positions, snapshotted at
sampled blocks. Built by replaying events.

| Column | Type | Description |
|---|---|---|
| `market_id` | string | Foreign key |
| `borrower` | string | Address |
| `block_number` | uint64 | Snapshot block |
| `block_ts` | timestamp\[ns, tz=UTC\] | |
| `borrow_shares` | float64 | Shares (note: not assets, assets derived via current rate) |
| `collateral` | float64 | Collateral pledged (collateral-asset units) |
| `borrow_assets` | float64 | Assets at the snapshot block (computed) |
| `ltv` | float64 | Loan-to-value, computed at snapshot using oracle price |
| `health_factor` | float64 | $\Lambda / \text{LTV}$ |

### 3.5 `oracle_prices.parquet`

| Column | Type | Description |
|---|---|---|
| `market_id` | string | Foreign key |
| `block_number` | uint64 | |
| `block_ts` | timestamp\[ns, tz=UTC\] | |
| `price` | float64 | Price collateral-per-loan, normalised |
| `price_decimals_raw` | int8 | Raw decimals on the oracle (informational) |
| `oracle_kind` | string | `chainlink`, `pyth`, etc. |
| `staleness_blocks` | int32 | Block delta since last on-chain update |

### 3.6 `dex_slippage.parquet`

Calibration data for the slippage curve $\pi(C, V)$.

| Column | Type | Description |
|---|---|---|
| `collateral_symbol` | string | `wstETH`, `WBTC`, etc. |
| `quote_ts` | timestamp\[ns, tz=UTC\] | |
| `direction` | string | `sell_collateral_for_loan` |
| `volume_usd` | float64 | Notional in U.S. dollars |
| `volume_native` | float64 | Volume in collateral-asset native units |
| `oracle_price` | float64 | Oracle price at quote time (U.S. dollars) |
| `realized_price` | float64 | Realised decentralised-exchange execution price (U.S. dollars) |
| `slippage_bps` | float64 | $(\text{oracle} - \text{realised}) / \text{oracle} \times 10000$, basis points |
| `source` | string | `1inch_quote`, `uniswap_swap`, or `cowswap_fill` |

---

## 4. Acquisition modules

Each module is a standalone, idempotent Python script under
`scripts/`. The script:

1. Reads configuration (markets list, block ranges) from
   `config.yaml`;
2. Fetches from one canonical source;
3. Writes to `data/raw/<source>/`;
4. Transforms into the Parquet schema above;
5. Writes to `data/cache/`;
6. Logs a manifest entry to `data/manifest.json`.

| Module | Script | Source |
|---|---|---|
| Markets | `scripts/fetch_markets.py` | RPC and subgraph |
| Market-state time series | `scripts/fetch_market_state.py` | RPC `eth_call` on `Morpho.market(id)` |
| Events | `scripts/fetch_events.py` | Subgraph paginated |
| Oracle prices | `scripts/fetch_oracle_prices.py` | RPC `latestRoundData` per block sample |
| Decentralised-exchange slippage (forward) | `scripts/fetch_dex_quotes.py` | 1inch application programming interface |
| Decentralised-exchange slippage (historical) | `scripts/fetch_uniswap_swaps.py` | Uniswap V3 subgraph |
| Total Value Locked | `scripts/fetch_tvl.py` | DeFiLlama application programming interface |

### 4.1 Idempotence rule

Re-running any script with the same configuration must produce
**bit-identical output Parquet** if upstream data has not changed.
Implementation: each script writes a sidecar `.checksum` file; a
preflight check skips re-fetch if checksums match.

### 4.2 Reorganisation safety

All RPC reads are at block heights at least `latest - 32` (Ethereum
chain reorganisation depth in practice is approximately 6 to 12; we
use 32 for safety).

---

## 5. Validation pipeline

Three layers, all driven by `pytest`. Failure halts the pipeline.

### 5.1 Schema validation

Per Parquet file, on write:

```python
import pyarrow.parquet as pq

table = pq.read_table(path)
schema_expected = SCHEMAS[table_name]
assert table.schema.equals(schema_expected, check_metadata=False)
```

### 5.2 Cross-source validation

Per category, sample $N = 50$ random rows and cross-check against the
secondary source. Threshold: a maximum 1% of rows in disagreement, a
maximum 5-basis-point relative error per row for prices.

| Category | Primary | Secondary | Tolerance |
|---|---|---|---|
| Market state | RPC | Subgraph (eventually-consistent) | 0.1% on `total_supply_assets` |
| Oracle prices | RPC `latestRoundData` | Off-chain centralised-exchange | 30 basis points (allows for funding gaps) |
| Liquidations | Subgraph events | RPC `eth_getLogs` | Exact match (event count) |

### 5.3 Sanity invariants

- For every row in `market_state`: `total_borrow_assets <= total_supply_assets`;
- For every position: `borrow_shares >= 0`, `collateral >= 0`;
- Aggregate cross-check: `sum(positions.borrow_shares) ≈ market_state.total_borrow_shares` per market per block (drift below 1%);
- Event counts monotonic in time.

---

## 6. DuckDB catalog

A single `data/catalog.duckdb` file exposes Parquet files as views
for ad-hoc analysis.

```sql
-- Auto-generated by scripts/build_catalog.py
CREATE VIEW markets         AS SELECT * FROM read_parquet('data/cache/markets.parquet');
CREATE VIEW market_state    AS SELECT * FROM read_parquet('data/cache/market_state.parquet');
CREATE VIEW events_supply   AS SELECT * FROM read_parquet('data/cache/events_supply.parquet');
-- etc.
```

Usage from Python:

```python
import duckdb
con = duckdb.connect("data/catalog.duckdb", read_only=True)
df = con.execute("""
  SELECT block_ts, total_supply_assets, total_borrow_assets,
         total_borrow_assets / NULLIF(total_supply_assets, 0) AS utilization
  FROM market_state
  WHERE market_id = ?
  ORDER BY block_ts
""", [market_id]).df()
```

---

## 7. Manifest

The file `data/manifest.json` records every successful pipeline run:

```json
{
  "schema_version": "0.1",
  "runs": [
    {
      "run_id": "2026-05-04T08-00-00Z",
      "config_hash": "sha256:...",
      "block_range_min": 21900000,
      "block_range_max": 22100000,
      "markets": ["0xabc...", "0xdef..."],
      "files": {
        "markets.parquet": {"sha256": "...", "rows": 17, "bytes": 12450},
        "market_state.parquet": {"sha256": "...", "rows": 4128, "bytes": 318901}
      },
      "validation": {"all_passed": true, "warnings": []}
    }
  ]
}
```

This lets Phase-3 modelling code pin to a specific data version and
detect drift.

---

## 8. Top-three initial lending markets

Frozen via `scripts/select_markets.py` on day one of Phase 2.
Selection rule:

1. Top-N by Total Value Locked on
   `defillama.com/protocol/morpho-blue` filtered to Ethereum mainnet;
2. Age greater than 6 months (sufficient history for 99th-percentile
   calibration);
3. Coverage of distinct collateral risk profiles.

Expected (subject to validation at run time):

- **wstETH/USDC**, wrapped-staked-Ether collateral, deepest Total
  Value Locked;
- **WBTC/USDC**, wrapped-Bitcoin collateral;
- **sUSDe/USDC**, yield-bearing stablecoin collateral
  (stress-relevant).

The top-five extension at Phase 2 close adds two more lending
markets, likely wstETH/WETH and cbBTC/USDC.

---

## 9. Configuration

The repository root holds `config.yaml`:

```yaml
# config.yaml — TEMPLATE
# Copy to config.local.yaml and fill in secrets via environment variables.

network:
  chain_id: 1
  rpc_url: "https://eth-mainnet.g.alchemy.com/v2/${ALCHEMY_KEY}"
  rpc_url_fallback: "https://eth.llamarpc.com"

morpho_blue:
  contract: "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFFb"  # placeholder

subgraph:
  url: "https://api.thegraph.com/subgraphs/name/morpho-org/morpho-blue"
  api_key: "${GRAPH_API_KEY}"

oneinch:
  api_url: "https://api.1inch.dev/swap/v6.0/1"
  api_key: "${ONEINCH_API_KEY}"

sampling:
  market_state_period_blocks: 1800     # approximately 6 hours on Ethereum
  oracle_price_period_blocks: 300      # approximately 1 hour
  position_snapshot_period_blocks: 7200  # approximately daily

range:
  start_ts: "2025-05-01T00:00:00Z"
  end_ts: "2026-05-01T00:00:00Z"

markets: []
```

Secrets via environment variables only, never committed.

---

## 10. Time and resource budget

| Module | Estimated work | Compute cost |
|---|---|---|
| `fetch_markets.py` | 1 hour | Below 100 RPC calls |
| `fetch_market_state.py` | 3 hours of development plus 1 hour of compute | Approximately 5,000 RPC calls per market over 12 months at 6-hour cadence |
| `fetch_events.py` | 2 hours of development plus 30 minutes of compute | Subgraph paginated, approximately 10,000 to 30,000 events per market |
| `fetch_oracle_prices.py` | 2 hours of development plus 2 hours of compute | Approximately 9,000 RPC calls per market |
| `fetch_dex_quotes.py` | 2 hours of development | 1inch free tier rate-limited; approximately 500 quotes |
| `fetch_uniswap_swaps.py` | 1 hour of development plus 30 minutes of compute | Subgraph |
| `fetch_tvl.py` | 30 minutes | DeFiLlama free |
| Validation suite | 2 hours |, |
| **Total** | **Approximately 14 to 16 hours** | Within Alchemy's free tier |

---

## 11. Forward references

After Phase 2 completes, Phase 3 reads exclusively from
`data/cache/*.parquet` and `data/catalog.duckdb`. No model code
touches a vendor application programming interface directly.

---

## 12. Document version control

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-05-04 | Initial Phase 2 specification |
| 0.2 | 2026-05-05 | All abbreviations spelled out at first use; companion `GLOSSARY.md` published |
