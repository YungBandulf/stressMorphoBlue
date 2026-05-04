# Phase 2 — Scripts

Each script is a standalone, idempotent CLI entry point.
All read configuration from `config.local.yaml` (or a path passed via `--config`).

## Implementation status

| Script | Role | Status |
|---|---|---|
| `select_markets.py` | Pick top-N markets from DeFiLlama, freeze IDs into `config.local.yaml` | ⏳ stub pending |
| `fetch_markets.py` | Read market params via RPC; write `markets.parquet` | ⚠ skeleton — orchestration done, ABI calls stubbed |
| `fetch_market_state.py` | Time series of market state via `eth_call` per block sample | ⏳ stub pending |
| `fetch_events.py` | Supply/Withdraw/Borrow/Repay/Liquidate events via subgraph paginated | ⏳ stub pending |
| `fetch_oracle_prices.py` | Per-block oracle reads | ⏳ stub pending |
| `fetch_dex_quotes.py` | 1inch quotes for slippage calibration | ⏳ stub pending |
| `fetch_uniswap_swaps.py` | Historical fills from Uniswap v3 subgraph | ⏳ stub pending |
| `build_catalog.py` | Build/refresh the DuckDB catalog over Parquet files | ⏳ stub pending |

## Run order

The scripts are designed to run in this order, but each is idempotent so partial reruns are safe:

```bash
python scripts/select_markets.py    # produces config.local.yaml with frozen markets
python scripts/fetch_markets.py     # markets.parquet
python scripts/fetch_market_state.py
python scripts/fetch_events.py
python scripts/fetch_oracle_prices.py
python scripts/fetch_dex_quotes.py
python scripts/fetch_uniswap_swaps.py
python scripts/build_catalog.py     # final DuckDB views
```

## Why most scripts are stubs

This repo's Phase 2 pull request establishes:

1. **Architecture** — schemas, storage, manifest, config, RPC and subgraph clients
2. **Tests** — unit-tested storage layer with strict schema validation
3. **One end-to-end harness** — `fetch_markets.py` shows the canonical flow

The remaining scripts will fill in the same template; each addition is a
self-contained PR for review. Implementing them all in one shot before
validating the architecture against real data would be premature.
