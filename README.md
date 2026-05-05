# Morpho Blue — Liquidity Stress Testing Framework

> A Basel III–inspired liquidity stress testing framework applied to Morpho Blue isolated lending markets and MetaMorpho vaults.

**Status**: Phase 0 — methodological draft. Not production-ready. Not investment advice.

---

## Motivation

DeFi lending pools are inherently fragile under stress (Chiu et al., BIS 2023), yet most public risk reporting on DeFi protocols transposes Basel concepts informally. This project formalizes a Basel III–equivalent liquidity stress framework for Morpho Blue, with two contributions:

1. An explicit on-chain analogue of the **Liquidity Coverage Ratio (LCR)** and **Net Stable Funding Ratio (NSFR)**, with stated mapping limitations.
2. A first quantitative measure of **MetaMorpho curator risk discipline** — the gap between observed allocation and the allocation that minimizes 30-day liquidity Value-at-Risk under the framework.

The work is calibrated on the April 2026 KelpDAO event as a primary stress anchor, alongside the March 2023 USDC depeg and the May 2022 stETH discount.

---

## Repository structure

```
morpho-blue-liquidity-stress/
├── docs/
│   ├── METHODOLOGY.md       # Core methodological note (start here)
│   └── references.md        # Annotated bibliography
├── src/                     # Python implementation (Phase 2+)
├── data/                    # Local Parquet cache (Phase 2+)
├── notebooks/               # Reproducible analyses (Phase 3+)
├── scripts/                 # Data acquisition entry points (Phase 2+)
├── tests/                   # pytest suite (Phase 2+)
└── README.md
```

---

## Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| **0** | Methodological note (`docs/METHODOLOGY.md`) | ✅ v0.2 |
| **1** | Stress scenario formalization (`docs/SCENARIOS.md`) | ✅ v0.1 |
| **2** | Data acquisition architecture (`docs/DATA.md`) + storage layer + tests | ✅ partial — architecture done, fetch scripts as skeletons |
| **3** | Modeling: IRM static + slippage + S1 + liquidation engine + mock data | ✅ done |
| **3.5** | IRM full adaptive + Uniswap V3 geometric TWAP + S3 + Monte Carlo + Hypothesis | ✅ done |
| **4** | Historical backtest framework (`docs/BACKTEST.md`) + 3 event fixtures | ✅ done — 3/3 events processed |
| **5** | v0.3 framework (LCR refactored, alpha calibrated) + slippage fit + forward-looking + writeup (`docs/REPORT.md`) | ✅ done — sUSDe/USDC identified as dominant tail risk |
| **6** | Public deliverables (Dune dashboard, Mirror article publication, X thread) | ⏳ pending publication |

## Quick start

```bash
# Install (using uv, the recommended Python package manager)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run the test suite (112 tests, ~3s)
PYTHONPATH=src pytest tests/ -v

# Run the Phase 3.5 end-to-end demo
PYTHONPATH=src python notebooks/phase35_demo.py

# Set up local config (for Phase 2 data acquisition, when fetchers are implemented)
cp config.yaml config.local.yaml  # then edit to add secrets via env vars
```

---

## How to read this repo (for reviewers / employers)

If you have **5 minutes**: read [`docs/METHODOLOGY.md`](./docs/METHODOLOGY.md) §1–2 and §4. That is the entire intellectual contribution at the methodology layer.

If you have **30 minutes**: read the full methodology note and skim the bibliography in [`docs/references.md`](./docs/references.md) to assess the academic grounding.

If you have **2 hours**: clone the repo (when implementation phases land), reproduce the dashboard end-to-end from `scripts/`, and verify the stress test on the KelpDAO replay scenario.

---

## Methodological positioning

| Reference | Approach | Our positioning |
|---|---|---|
| Gauntlet, Chaos Labs | Agent-based simulation of liquidations | We are simpler (deterministic stress shocks at empirical quantiles) and explicitly acknowledge this gap; targeted as v1. |
| LlamaRisk, Block Analitica | Descriptive risk reports per market | We provide an explicit Basel mapping and a falsifiable hypothesis structure that they do not. |
| Chiu et al. (BIS 2023) | Theoretical model of DeFi run dynamics | We are empirical / applied; their model justifies our framework's relevance but our work is implementation-oriented. |
| Steakhouse Financial | Vault-curator centric | Our hypothesis 2 explicitly targets curator risk discipline as a quantifiable gap — a question they engage with operationally but do not formalize. |

---

## License

MIT (to be confirmed before public release).

## Disclaimer

This work is academic and exploratory. It is not investment advice, not a recommendation to deposit on or borrow from any Morpho Blue market, and not a substitute for a security audit or formal risk assessment. The author has no affiliation with Morpho Labs, MetaMorpho curators, or any protocol mentioned, beyond public usage.
