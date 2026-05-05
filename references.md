# References

Annotated bibliography for the Morpho Blue liquidity stress testing framework.

> Convention: each entry includes a relevance tag and a one-line note on how it is used in the methodology.

---

## A. Basel III / Bank regulatory framework (foundational)

### A.1 BCBS 238 — Basel III: The Liquidity Coverage Ratio and liquidity risk monitoring tools (2013)

- Bank for International Settlements, January 2013
- URL: https://www.bis.org/publ/bcbs238.htm
- **Used for**: definition of HQLA tiers, runoff factors, and the LCR formula transposed in §2.1.

### A.2 BCBS 295 — Basel III: The Net Stable Funding Ratio (2014)

- Bank for International Settlements, October 2014
- URL: https://www.bis.org/bcbs/publ/d295.htm
- **Used for**: ASF / RSF weights and the structural argument in §2.3 that DeFi lending pools have a degenerate NSFR.

### A.3 BCBS 144 — Principles for Sound Liquidity Risk Management and Supervision (2008)

- Bank for International Settlements, September 2008
- URL: https://www.bis.org/publ/bcbs144.htm
- **Used for**: qualitative framing of stress scenarios (S1–S4 are inspired by §145–147 of this document).

---

## B. DeFi lending — academic literature

### B.1 Gudgeon, Werner, Perez & Knottenbelt (2020) — "DeFi Protocols for Loanable Funds: Interest Rates, Liquidity and Market Efficiency"

- *Financial Cryptography 2020 (FC '20)*, AFT '20 (also presented)
- arXiv: https://arxiv.org/abs/2006.13922
- **Used for**: formal model of DeFi lending interest rate dynamics; baseline for IRM behavior under stress.

### B.2 Capponi & Jia (2021, 2023)

- Capponi, A., & Jia, R. — "The Adoption of Blockchain-based Decentralized Exchanges" + follow-up work on liquidations and DeFi runs
- Available via Columbia Business School working paper series
- **Used for**: theoretical justification for treating endogeneity as the key v1 extension (§4.1).

### B.3 Chiu, Ozdenoren, Yuan & Zhang — "On the inherent fragility of DeFi lending"

- BIS Working Paper 1062, January 2023
- URL: https://www.bis.org/publ/work1062.htm
- **Used for**: closest existing formal model of DeFi lending fragility; benchmark against which our empirical framework is positioned.

### B.4 Lehar & Parlour — "Liquidity Provision in Decentralized Exchanges"

- *Review of Finance*, working paper series
- **Used for**: DEX liquidity modeling that feeds the slippage-adjusted HQLA computation.

### B.5 Qin, Zhou, Livshits & Gervais (2021) — "Attacking the DeFi Ecosystem with Flash Loans for Fun and Profit"

- *Financial Cryptography 2021*
- arXiv: https://arxiv.org/abs/2003.03810
- **Used for**: illustration of attack-driven stress; informs scenario S4 (cascade) parameterization.

---

## C. Protocol specifications

### C.1 Morpho Blue Whitepaper

- Morpho Labs, 2024 (latest version)
- URL: https://github.com/morpho-org/morpho-blue/blob/main/morpho-blue-whitepaper.pdf
- **Used for**: protocol mechanics — supply, borrow, liquidation, IRM specification.

### C.2 Morpho Blue Yellow Paper

- Morpho Labs
- URL: https://github.com/morpho-org/morpho-blue (repository documentation)
- **Used for**: implementation-level details — share accounting, accrual, market parameters.

### C.3 MetaMorpho documentation

- Morpho Labs, Morpho Vaults docs
- URL: https://docs.morpho.org
- **Used for**: vault curator allocation mechanics; basis for hypothesis 2 (§1.2).

---

## D. Industry references — risk reports (style and benchmarks)

### D.1 Steakhouse Financial — MakerDAO public analyses

- Steakhouse public reports (2023–2026)
- URL: https://steakhouse.financial
- **Used for**: gold standard for risk-report format; we deliberately emulate the structure (executive summary → methodology → findings → limits).

### D.2 Block Analitica — Maker/Spark risk reports

- Block Analitica
- URL: https://blockanalitica.com
- **Used for**: quantitative reporting style, especially for parameter recommendations.

### D.3 LlamaRisk — Aave V3 and Curve risk reports

- LlamaRisk DAO
- URL: https://www.llamarisk.com
- **Used for**: direct competitor in the same niche — used as upper benchmark on rigor and as critical reference (we explicitly identify their methodological gaps).

### D.4 Gauntlet — Aave / Compound governance risk parameter recommendations

- Gauntlet, ongoing forum posts on Aave Governance and Compound Governance
- URL: https://gauntlet.network and https://governance.aave.com/u/Gauntlet
- **Used for**: parameter-recommendation format; benchmark for agent-based simulation rigor (acknowledged as superior to our v0 approach).

### D.5 Chaos Labs — Risk Oracle and protocol risk monitoring

- Chaos Labs reports
- URL: https://chaoslabs.xyz
- **Used for**: real-time monitoring approach; benchmark for the "live dashboard" component of the deliverable.

---

## E. Data sources

### E.1 Dune Analytics — Morpho Blue queries

- Dune Analytics
- URL: https://dune.com
- **Used for**: aggregated on-chain data via SQL queries (custom queries written for this project, no fork of community queries).

### E.2 The Graph — Morpho Blue subgraph

- The Graph protocol
- **Used for**: event-level historical data for borrowers, suppliers, liquidations.

### E.3 DeFiLlama — Morpho Blue protocol page

- URL: https://defillama.com/protocol/morpho-blue
- **Used for**: market selection (top-N by TVL) and TVL time series.

### E.4 1inch / Uniswap v3 / CoW Swap — DEX liquidity

- 1inch Pathfinder API, Uniswap v3 ticks, CoW Swap
- **Used for**: realized DEX slippage estimation feeding HQLA Level 2A/2B haircut computation.

### E.5 Chainlink, Pyth, Redstone — oracle feeds

- Per-market oracle source as defined in the Morpho Blue market parameters
- **Used for**: historical oracle prices and deviation-from-market detection.

---

## F. Stress event historical data

### F.1 KelpDAO exploit — April 2026

- Coverage: multiple sources, including post-mortem from Aave governance forum
- **Used for**: primary calibration anchor for scenario S5.

### F.2 USDC depeg — March 2023

- SVB collapse impact on Circle reserves; USDC traded at ~0.88 USD briefly
- **Used for**: calibration of scenario S3 (oracle deviation under stable depeg).

### F.3 stETH discount — May 2022

- Lido stETH traded at discount to ETH (~0.94 stETH/ETH peak gap)
- **Used for**: calibration of scenario S3 for LST collateral types.

### F.4 Mango Markets attack — October 2022 (illustrative only)

- Oracle manipulation case study
- **Used for**: qualitative reference on oracle-attack vectors; not used in calibration.
