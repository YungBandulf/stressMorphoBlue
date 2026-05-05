# Morpho Blue — Liquidity Stress Testing Framework

> A liquidity stress testing framework for Morpho Blue isolated
> lending markets and MetaMorpho vaults, adapted from Basel III
> regulatory standards (specifically the Liquidity Coverage Ratio of
> document BCBS 238, 2013).

**Status**: methodological draft. Not production-ready. Not investment
advice.

---

## A note on terminology

Every specialised term used in this repository is defined in
[`docs/GLOSSARY.md`](./docs/GLOSSARY.md). Mathematical symbols are
introduced with their units. Abbreviations are spelled out on first
use, with the abbreviation in parentheses. Documentation files do not
assume reader familiarity with either institutional finance or
decentralised-finance jargon.

---

## Motivation

Decentralised-finance lending pools have been shown to exhibit
inherent fragility under stress (Chiu, Ozdenoren, Yuan & Zhang, *On
the inherent fragility of decentralised-finance lending*, Bank for
International Settlements Working Paper 1062, 2023). Yet most public
risk reports for these pools transpose Basel concepts informally,
without explicit pass-or-fail criteria, and without a reproducible
backtest against historical events.

This project formalises the transposition for Morpho Blue, a
non-custodial lending protocol with isolated lending markets and
immutable parameters. It contributes:

1. An explicit on-chain analogue of the **Liquidity Coverage Ratio**
   (the regulatory ratio defined by the Basel Committee on Banking
   Supervision in document BCBS 238, 2013), with stated mapping
   limitations;

2. A first quantitative measure of **MetaMorpho vault curator risk
   discipline** — the gap between observed allocation and the
   allocation that minimises 30-day liquidity Value-at-Risk under the
   framework.

The work is calibrated on the KelpDAO collateral exploit of April
2026 as a primary stress anchor, alongside the USDC depeg of March
2023 and the staked-Ether discount episode of May 2022.

---

## Repository structure

```
morpho-blue-liquidity-stress/
├── docs/
│   ├── GLOSSARY.md          # Definitions of all specialised terms
│   ├── METHODOLOGY.md       # Core methodological note
│   ├── SCENARIOS.md         # Stress-scenario specification
│   ├── DATA.md              # Data architecture
│   ├── BACKTEST.md          # Backtest specification
│   ├── REPORT.md            # Public writeup (Mirror.xyz-ready)
│   └── references.md        # Annotated bibliography
├── src/                     # Python implementation
├── data/                    # Local Parquet cache (gitignored) and event fixtures
├── notebooks/               # Reproducible analyses
├── scripts/                 # Data-acquisition entry points
├── tests/                   # pytest suite
└── README.md
```

---

## Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| **0** | Methodological note (`docs/METHODOLOGY.md`) | Done — version 0.3 |
| **1** | Stress-scenario formalisation (`docs/SCENARIOS.md`) | Done — version 0.2 |
| **2** | Data-acquisition architecture (`docs/DATA.md`), storage layer, and tests | Partial — architecture done, fetch scripts as skeletons |
| **3** | Modelling: AdaptiveCurveIRM, slippage curve, S1 (withdrawal run), liquidation engine | Done |
| **3.5** | AdaptiveCurveIRM full-adaptive layer, geometric Time-Weighted Average Price oracle, S3 (oracle deviation), Monte Carlo, property-based tests | Done |
| **4** | Historical-backtest framework (`docs/BACKTEST.md`) and three event fixtures | Done — three of three events processed |
| **5** | Version-0.3 framework (Liquidity Coverage Ratio refactored, outflow fraction event-calibrated), slippage curve fitted with diagnostics, forward-looking analysis, public writeup (`docs/REPORT.md`) | Done — sUSDe/USDC identified as dominant tail risk |
| **6** | Public deliverables (Dune dashboard, Mirror article publication, social-media thread) | Pending publication |

---

## Quick start

```bash
# Install (using uv, the recommended Python package manager)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run the test suite (145 tests, approximately 90 seconds)
PYTHONPATH=src pytest tests/ -v

# Run the Phase-5 end-to-end demonstration
PYTHONPATH=src python notebooks/phase5_demo.py

# Set up local configuration (for Phase-2 data acquisition, when fetchers are implemented)
cp config.yaml config.local.yaml  # then edit to add secrets via environment variables
```

---

## How to read this repository (for reviewers and prospective employers)

If you have **5 minutes**: read [`docs/REPORT.md`](./docs/REPORT.md)
sections 1, 4, and 5. That is the framework's headline finding, the
forward-looking ranking, and the explicit limitations.

If you have **30 minutes**: read [`docs/REPORT.md`](./docs/REPORT.md)
end-to-end, then skim the bibliography in
[`docs/references.md`](./docs/references.md) and the glossary in
[`docs/GLOSSARY.md`](./docs/GLOSSARY.md) to assess academic grounding.

If you have **2 hours**: clone the repository, run the test suite,
and reproduce the Phase-5 demonstration. Inspect the v0.3 Liquidity
Coverage Ratio implementation in
`src/morpho_stress/backtest/liquidity_metrics.py` and the
event-calibrated outflow fraction.

---

## Methodological positioning

| Reference | Approach | Our positioning |
|---|---|---|
| Gauntlet, ChaosLabs | Agent-based simulation of liquidations | We use deterministic stress shocks at empirical quantiles plus a Monte Carlo layer; explicitly acknowledged simpler than agent-based; targeted as a future extension. |
| LlamaRisk, Block Analitica | Descriptive risk reports per market | We provide an explicit Basel-III mapping and a falsifiable hypothesis structure that they do not. |
| Chiu, Ozdenoren, Yuan, Zhang (BIS Working Paper 1062, 2023) | Theoretical model of decentralised-finance run dynamics | We are empirical and applied; their model justifies our framework's relevance, but our work is implementation-oriented. |
| Steakhouse Financial | Vault-curator-centric reporting | Our secondary hypothesis explicitly targets curator risk discipline as a quantifiable gap — a question they engage with operationally but do not formalise. |

---

## License

MIT (to be confirmed before public release).

## Disclaimer

This work is academic and exploratory. It is not investment advice;
not a recommendation to deposit on or borrow from any Morpho Blue
lending market; not a substitute for a security audit or formal risk
assessment. The author has no affiliation with Morpho Labs,
MetaMorpho vault curators, or any protocol mentioned, beyond public
usage.
