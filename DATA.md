# Data Architecture — Phase 2

> Version: 0.1 — Last updated: May 2026
> Status: Phase 2 deliverable — data acquisition specification and implementation
> Scope: top-3 markets initially, extension to top-5 at Phase 2 close

---

## 1. Source-of-Truth Map

Each data category has **exactly one canonical source**. Cross-source validation is performed but never triggers data fusion at the storage layer.

| Category | Canonical source | Why | Validation source |
|---|---|---|---|
| Market state (S, B, supply/borrow shares, accruals) | RPC (`eth_call` on `Morpho` contract) at block heights | Exact, deterministic, reorg-safe at depth ≥ 32 | Subgraph (latency + reorg risk) |
| Events (Supply, Withdraw, Borrow, Repay, Liquidate) | Subgraph (Morpho hosted) | Native event indexing | RPC `eth_getLogs` for spot validation |
| Oracle prices (per market oracle config) | RPC `latestRoundData` for Chainlink, equivalent for Pyth/Redstone | Same oracle the contract reads | Off-chain CEX feed (Binance, Coinbase) |
| DEX liquidity & realized slippage | 1inch quote API (forward) + Uniswap v3 historical swaps via subgraph (backward) | Forward-looking quotes feed scenarios; historical fills feed calibration | Cross-check via CoW Swap fills |
| Aggregate TVL / market metadata | DeFiLlama API | Single endpoint, cached | DeFiLlama HTML page |
| Liquidation history (executed) | Subgraph `Liquidate` events | Native | RPC `eth_getLogs` |
| MetaMorpho vault allocations | RPC `MetaMorpho.config()` and balance queries | Exact | Subgraph |

**Rule**: when modeling code reads `liquidations`, it reads from `data/parquet/liquidations.parquet`, never directly from a vendor. The data layer is the API.

---

## 2. Storage Layout

```
data/
├── raw/                          # Immutable raw dumps (never edited, gitignored)
│   ├── dune/                     # CSV exports from Dune queries
│   ├── subgraph/                 # GraphQL response JSON (gzipped)
│   ├── rpc/                      # Block-state RPC responses (JSON-LD)
│   ├── oracle/                   # Per-block oracle reads
│   └── dex/                      # 1inch quotes + Uniswap swaps
├── cache/                        # Derived Parquet files (regeneratable, gitignored)
│   ├── markets.parquet           # Market metadata (immutable Morpho Blue params)
│   ├── market_state.parquet      # Time series of (S, B, U) per market per block sample
│   ├── events_supply.parquet
│   ├── events_withdraw.parquet
│   ├── events_borrow.parquet
│   ├── events_repay.parquet
│   ├── events_liquidate.parquet
│   ├── positions.parquet         # Reconstructed positions per (market, borrower)
│   ├── oracle_prices.parquet     # Per-market oracle price time series
│   ├── dex_slippage.parquet      # Calibration data for π(C, V)
│   └── tvl_daily.parquet         # DeFiLlama TVL history
├── catalog.duckdb                # DuckDB views over Parquet for SQL access
└── .gitkeep
```

---

## 3. Schema Specifications

All Parquet files use **strict typed schemas with PyArrow**. Type drift = test failure.

### 3.1 `markets.parquet`

Immutable Morpho Blue market parameters (one row per market, ~few hundred rows total).

| Column | Type | Description |
|---|---|---|
| `market_id` | string | Morpho Blue market id (32-byte hash, hex-encoded with `0x`) |
| `loan_asset` | string | Loan asset address, lowercase hex |
| `loan_asset_symbol` | string | Symbol (USDC, WETH, ...) |
| `loan_asset_decimals` | int8 | Decimals of loan asset |
| `collateral_asset` | string | Collateral asset address |
| `collateral_asset_symbol` | string | Symbol |
| `collateral_asset_decimals` | int8 | Decimals |
| `oracle` | string | Oracle contract address |
| `oracle_type` | string | Categorical: `chainlink`, `pyth`, `redstone`, `uniswap_twap`, `composite` |
| `irm` | string | IRM contract address |
| `lltv` | float64 | Liquidation LTV (0 to 1) |
| `created_at_block` | uint64 | Block of `CreateMarket` event |
| `created_at_ts` | timestamp[ns, tz=UTC] | Wall time |

### 3.2 `market_state.parquet`

Time series of market state. Sampled at **6h cadence** by default; dense around stress events.

| Column | Type | Description |
|---|---|---|
| `market_id` | string | FK → `markets.market_id` |
| `block_number` | uint64 | Ethereum block |
| `block_ts` | timestamp[ns, tz=UTC] | Wall time |
| `total_supply_assets` | float64 | Loan asset supplied (in loan asset native units, decimals applied) |
| `total_supply_shares` | float64 | Supply shares total |
| `total_borrow_assets` | float64 | Loan asset borrowed |
| `total_borrow_shares` | float64 | Borrow shares total |
| `total_collateral` | float64 | Collateral pool (collateral asset units) |
| `last_update` | uint64 | Contract `lastUpdate` field (block) |
| `fee` | float64 | Market fee (0 to 1) |

Constraints (validated):
- `total_borrow_assets <= total_supply_assets` (cannot over-borrow)
- `block_ts` strictly increasing per market
- No NaN in mandatory columns

### 3.3 `events_supply.parquet`, `events_withdraw.parquet`, `events_borrow.parquet`, `events_repay.parquet`

Supplier and borrower events.

| Column | Type | Description |
|---|---|---|
| `market_id` | string | FK |
| `block_number` | uint64 |  |
| `block_ts` | timestamp[ns, tz=UTC] |  |
| `tx_hash` | string |  |
| `log_index` | uint32 | For exact event ordering |
| `caller` | string | `msg.sender`, lowercase address |
| `on_behalf` | string | `onBehalf` parameter (the actual user) |
| `receiver` | string | Asset receiver (Withdraw / Borrow only) |
| `assets` | float64 | Amount in loan asset units |
| `shares` | float64 | Amount in share units |

### 3.4 `events_liquidate.parquet`

Liquidations — the highest-stakes event for the framework.

| Column | Type | Description |
|---|---|---|
| `market_id` | string | FK |
| `block_number` | uint64 |  |
| `block_ts` | timestamp[ns, tz=UTC] |  |
| `tx_hash` | string |  |
| `log_index` | uint32 |  |
| `liquidator` | string | Liquidator address |
| `borrower` | string | Liquidated user |
| `repaid_assets` | float64 | Loan repaid by liquidator |
| `repaid_shares` | float64 | Borrow shares cleared |
| `seized_assets` | float64 | Collateral taken by liquidator |
| `bad_debt_assets` | float64 | Realized bad debt (positive ⇒ uncovered) |
| `bad_debt_shares` | float64 |  |

### 3.5 `positions.parquet`

Reconstructed per-(market, borrower) positions, snapshot at sampled blocks. Built by replaying events.

| Column | Type | Description |
|---|---|---|
| `market_id` | string | FK |
| `borrower` | string | Address |
| `block_number` | uint64 | Snapshot block |
| `block_ts` | timestamp[ns, tz=UTC] |  |
| `borrow_shares` | float64 | Shares (note: not assets — assets derived via current rate) |
| `collateral` | float64 | Collateral pledged |
| `borrow_assets` | float64 | Assets at snapshot block (computed) |
| `ltv` | float64 | Computed at snapshot (using oracle price) |
| `health_factor` | float64 | LLTV / LTV |

### 3.6 `oracle_prices.parquet`

| Column | Type | Description |
|---|---|---|
| `market_id` | string | FK |
| `block_number` | uint64 |  |
| `block_ts` | timestamp[ns, tz=UTC] |  |
| `price` | float64 | Price collateral / loan, normalized to 1e0 |
| `price_decimals_raw` | int8 | Raw decimals on the oracle (informational) |
| `oracle_kind` | string | `chainlink` / `pyth` / etc. |
| `staleness_blocks` | int32 | Block delta since last on-chain update |

### 3.7 `dex_slippage.parquet`

Calibration data for $\pi(C, V)$.

| Column | Type | Description |
|---|---|---|
| `collateral_symbol` | string | `wstETH`, `WBTC`, ... |
| `quote_ts` | timestamp[ns, tz=UTC] |  |
| `direction` | string | `sell_collateral_for_loan` |
| `volume_usd` | float64 | Notional in USD |
| `volume_native` | float64 | Volume in collateral native units |
| `oracle_price` | float64 | Oracle price at quote time (USD) |
| `realized_price` | float64 | Realized DEX execution price (USD) |
| `slippage_bps` | float64 | (oracle - realized) / oracle * 10000 |
| `source` | string | `1inch_quote` / `uniswap_swap` / `cowswap_fill` |

---

## 4. Acquisition Modules

Each module is a standalone, idempotent Python script under `scripts/` that:

1. Reads config (markets list, block ranges) from `config.yaml`
2. Fetches from one canonical source
3. Writes to `data/raw/<source>/`
4. Transforms into the Parquet schema above
5. Writes to `data/cache/`
6. Logs a manifest entry to `data/manifest.json`

| Module | Script | Source |
|---|---|---|
| Markets | `scripts/fetch_markets.py` | RPC + subgraph |
| Market state time series | `scripts/fetch_market_state.py` | RPC `eth_call` on `Morpho.market(id)` |
| Events | `scripts/fetch_events.py` | Subgraph paginated |
| Oracle prices | `scripts/fetch_oracle_prices.py` | RPC `latestRoundData` per block sample |
| DEX slippage (forward) | `scripts/fetch_dex_quotes.py` | 1inch API |
| DEX slippage (historical) | `scripts/fetch_uniswap_swaps.py` | Uniswap v3 subgraph |
| TVL | `scripts/fetch_tvl.py` | DeFiLlama API |

### Idempotence rule

Re-running any script with the same config must produce **bit-identical output Parquet** if upstream data hasn't changed. Implementation: each script writes a sidecar `.checksum` file; pre-flight check skips re-fetch if checksums match.

### Reorg safety

All RPC reads are at block heights ≥ `latest - 32` (Ethereum reorg depth in practice ~ 6–12, we use 32 for safety). Subgraph queries query by `block_number` not `latest`.

---

## 5. Validation Pipeline

Three layers, all pytest-driven. Failure halts pipeline.

### 5.1 Schema validation

Per Parquet file, on write:

```python
import pyarrow.parquet as pq
import pandera as pa  # or pyarrow direct schema check

table = pq.read_table(path)
schema_expected = SCHEMAS[table_name]
assert table.schema.equals(schema_expected, check_metadata=False)
```

### 5.2 Cross-source validation

Per category, sample N=50 random rows and cross-check against secondary source. Threshold: max 1% rows in disagreement, max 5 bps relative error per row for prices.

| Category | Primary | Secondary | Tolerance |
|---|---|---|---|
| Market state | RPC | Subgraph (eventually-consistent) | 0.1% on `total_supply_assets` |
| Oracle prices | RPC `latestRoundData` | Off-chain CEX | 30 bps (allows for funding gaps) |
| Liquidations | Subgraph events | RPC `eth_getLogs` | Exact match (event count) |

### 5.3 Sanity invariants

- For every market state row: `total_borrow_assets <= total_supply_assets`
- For every position: `borrow_shares >= 0`, `collateral >= 0`
- Aggregate cross-check: `sum(positions.borrow_shares) ≈ market_state.total_borrow_shares` per market per block (drift < 1%)
- Event counts monotonic in time

---

## 6. DuckDB Catalog

A single `data/catalog.duckdb` file exposes Parquet files as views for ad-hoc analysis.

```sql
-- Auto-generated by scripts/build_catalog.py
CREATE VIEW markets         AS SELECT * FROM read_parquet('data/cache/markets.parquet');
CREATE VIEW market_state    AS SELECT * FROM read_parquet('data/cache/market_state.parquet');
CREATE VIEW events_supply   AS SELECT * FROM read_parquet('data/cache/events_supply.parquet');
-- ... etc
```

Usage from Python (zero-copy where possible):

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

`data/manifest.json` records every successful pipeline run:

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
        "market_state.parquet": {"sha256": "...", "rows": 4128, "bytes": 318901},
        "...": "..."
      },
      "validation": {"all_passed": true, "warnings": []}
    }
  ]
}
```

This lets Phase 3 modeling code pin to a specific data version and detect drift.

---

## 8. Top-3 Initial Markets

Frozen via `scripts/select_markets.py` on day 1 of Phase 2. Selection rule:

1. Top by TVL on `defillama.com/protocol/morpho-blue` filtered to Ethereum mainnet
2. Age > 6 months (sufficient history for p99 calibration)
3. Coverage of distinct collateral risk profiles

Expected (subject to validation at run time):

- `wstETH / USDC` — LST collateral, deepest TVL
- `WBTC / USDC` — BTC collateral
- `sUSDe / USDC` — yield-bearing stable (stress-relevant)

Top-5 extension at Phase 2 close adds 2 more, likely `wstETH/WETH` and `cbBTC/USDC`.

---

## 9. Configuration

`config.yaml` at the repo root:

```yaml
# config.yaml (template — copy to config.local.yaml and edit)

network:
  chain_id: 1
  rpc_url: "https://eth-mainnet.g.alchemy.com/v2/${ALCHEMY_KEY}"
  rpc_url_fallback: "https://eth.llamarpc.com"

morpho_blue:
  contract: "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFFb"  # placeholder, fetch from official docs

subgraph:
  url: "https://api.thegraph.com/subgraphs/name/morpho-org/morpho-blue"
  api_key: "${GRAPH_API_KEY}"  # optional for hosted, required for decentralized network

oneinch:
  api_url: "https://api.1inch.dev/swap/v6.0/1"
  api_key: "${ONEINCH_API_KEY}"

# Sample cadence
sampling:
  market_state_period_blocks: 1800   # ≈ 6 hours on Ethereum (12s/block)
  oracle_price_period_blocks: 300    # ≈ 1 hour
  position_snapshot_period_blocks: 7200  # ≈ daily

# Range
range:
  start_ts: "2025-05-01T00:00:00Z"
  end_ts: "2026-05-01T00:00:00Z"

# Markets (filled by select_markets.py)
markets: []
```

Secrets via env vars only, never committed.

---

## 10. Time / Resource Budget

| Module | Estimated work | Compute cost |
|---|---|---|
| `fetch_markets.py` | 1 h | < 100 RPC calls |
| `fetch_market_state.py` | 3 h dev + 1 h compute | ~5k RPC calls per market over 12 months at 6h cadence |
| `fetch_events.py` | 2 h dev + 30 min compute | Subgraph paginated, ~10–30k events per market |
| `fetch_oracle_prices.py` | 2 h dev + 2 h compute | ~9k RPC calls per market |
| `fetch_dex_quotes.py` | 2 h dev | 1inch free tier rate-limited; ~500 quotes |
| `fetch_uniswap_swaps.py` | 1 h dev + 30 min compute | Subgraph |
| `fetch_tvl.py` | 30 min | DeFiLlama free |
| Validation suite | 2 h | — |
| **Total** | **~14–16 h** | Within Alchemy free tier |

---

## 11. Forward References

After Phase 2 completes, Phase 3 reads exclusively from `data/cache/*.parquet` and `data/catalog.duckdb`. No model code touches a vendor API directly.
