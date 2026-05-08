# References

Annotated bibliography for the Morpho Blue liquidity stress testing
framework. Definitions of all specialised terms used below are in
[`GLOSSARY.md`](./GLOSSARY.md).

> Convention: each entry includes a relevance tag and a one-line note
> on how it is used in the methodology.

---

## A. Basel framework: institutional banking-regulation references

### A.1 BCBS 238: *Basel III: The Liquidity Coverage Ratio and liquidity risk monitoring tools* (2013)

- Bank for International Settlements, January 2013.
- Uniform Resource Locator: https://www.bis.org/publ/bcbs238.htm
- **Used for**: definition of High Quality Liquid Asset tiers, runoff
  factors, and the Liquidity Coverage Ratio formula transposed in
  [`METHODOLOGY.md`](./METHODOLOGY.md) §2.1.

### A.2 BCBS 295: *Basel III: The Net Stable Funding Ratio* (2014)

- Bank for International Settlements, October 2014.
- Uniform Resource Locator: https://www.bis.org/bcbs/publ/d295.htm
- **Used for**: Available-Stable-Funding and Required-Stable-Funding
  weights, and the structural argument in
  [`METHODOLOGY.md`](./METHODOLOGY.md) §2.5 that
  decentralised-finance lending pools have a degenerate Net Stable
  Funding Ratio.

### A.3 BCBS 144: *Principles for Sound Liquidity Risk Management and Supervision* (2008)

- Bank for International Settlements, September 2008.
- Uniform Resource Locator: https://www.bis.org/publ/bcbs144.htm
- **Used for**: qualitative framing of stress scenarios. Scenarios S1
  through S4 in [`SCENARIOS.md`](./SCENARIOS.md) are inspired by §145
  through §147 of this document.

---

## B. Decentralised-finance lending: academic literature

### B.1 Gudgeon, Werner, Perez, Knottenbelt (2020): *Decentralised-Finance Protocols for Loanable Funds: Interest Rates, Liquidity and Market Efficiency*

- *Financial Cryptography 2020 (FC '20)*, also presented at AFT '20.
- Uniform Resource Locator: https://arxiv.org/abs/2006.13922
- **Used for**: a formal model of decentralised-finance lending
  interest-rate dynamics; baseline for interest-rate-model behaviour
  under stress.

### B.2 Capponi, Jia (2021, 2023)

- Capponi, A., and Jia, R., *The Adoption of Blockchain-based
  Decentralised Exchanges*, plus follow-up work on liquidations and
  decentralised-finance runs.
- Available via the Columbia Business School working-paper series.
- **Used for**: theoretical justification for treating endogeneity as
  the key future-version extension (see
  [`METHODOLOGY.md`](./METHODOLOGY.md) §4.1).

### B.3 Chiu, Ozdenoren, Yuan, Zhang: *On the inherent fragility of decentralised-finance lending*

- Bank for International Settlements Working Paper 1062, January 2023.
- Uniform Resource Locator: https://www.bis.org/publ/work1062.htm
- **Used for**: the closest existing formal model of
  decentralised-finance lending fragility; the benchmark against which
  our empirical framework is positioned.

### B.4 Lehar, Parlour: *Liquidity Provision in Decentralised Exchanges*

- *Review of Finance*, working-paper series.
- **Used for**: decentralised-exchange liquidity modelling that feeds
  the slippage-adjusted High Quality Liquid Asset computation.

### B.5 Qin, Zhou, Livshits, Gervais (2021): *Attacking the Decentralised-Finance Ecosystem with Flash Loans for Fun and Profit*

- *Financial Cryptography 2021*.
- Uniform Resource Locator: https://arxiv.org/abs/2003.03810
- **Used for**: illustration of attack-driven stress; informs the S4
  cascade-scenario parameterisation.

---

## C. Protocol specifications

### C.1 Morpho Blue Whitepaper

- Morpho Labs, 2024 (latest version).
- Uniform Resource Locator: https://github.com/morpho-org/morpho-blue/blob/main/morpho-blue-whitepaper.pdf
- **Used for**: protocol mechanics, supply, borrow, liquidation,
  and interest rate model specification.

### C.2 Morpho Blue Yellow Paper

- Morpho Labs.
- Uniform Resource Locator: https://github.com/morpho-org/morpho-blue (repository documentation).
- **Used for**: implementation-level details, share accounting,
  accrual, market parameters.

### C.3 MetaMorpho documentation

- Morpho Labs, MetaMorpho-vault documentation.
- Uniform Resource Locator: https://docs.morpho.org
- **Used for**: vault-curator allocation mechanics; basis for the
  secondary hypothesis in [`METHODOLOGY.md`](./METHODOLOGY.md) §1.2.

---

## D. Industry references: risk reports (style and benchmarks)

### D.1 Steakhouse Financial: public Maker analyses

- Steakhouse public reports (2023 to 2026).
- Uniform Resource Locator: https://steakhouse.financial
- **Used for**: gold standard for risk-report format. We deliberately
  emulate the structure (executive summary, methodology, findings,
  limits).

### D.2 Block Analitica: Maker and Spark risk reports

- Block Analitica.
- Uniform Resource Locator: https://blockanalitica.com
- **Used for**: quantitative reporting style, especially for
  parameter recommendations.

### D.3 LlamaRisk: Aave V3 and Curve risk reports

- LlamaRisk decentralised-autonomous-organisation.
- Uniform Resource Locator: https://www.llamarisk.com
- **Used for**: a direct competitor in the same niche. Used both as
  an upper benchmark on rigour and as a critical reference (we
  identify their methodological gaps explicitly).

### D.4 Gauntlet: Aave and Compound governance risk-parameter recommendations

- Gauntlet, ongoing forum posts on the Aave Governance and Compound
  Governance forums.
- Uniform Resource Locator: https://gauntlet.network and https://governance.aave.com/u/Gauntlet
- **Used for**: parameter-recommendation format; benchmark for
  agent-based-simulation rigour (we acknowledge that Gauntlet's
  agent-based simulation is more sophisticated than our baseline).

### D.5 Chaos Labs: Risk Oracle and protocol-risk monitoring

- Chaos Labs reports.
- Uniform Resource Locator: https://chaoslabs.xyz
- **Used for**: real-time monitoring approach; benchmark for the
  "live dashboard" component of the deliverable.

---

## E. Data sources

### E.1 Dune Analytics: Morpho Blue queries

- Dune Analytics.
- Uniform Resource Locator: https://dune.com
- **Used for**: aggregated on-chain data via SQL queries (custom
  queries written for this project; no fork of community queries).

### E.2 The Graph: Morpho Blue subgraph

- The Graph protocol.
- **Used for**: event-level historical data for borrowers, suppliers,
  and liquidations.

### E.3 DeFiLlama: Morpho Blue protocol page

- Uniform Resource Locator: https://defillama.com/protocol/morpho-blue
- **Used for**: market selection (top-N by Total Value Locked) and
  Total-Value-Locked time series.

### E.4 1inch, Uniswap V3, CoW Swap: decentralised-exchange liquidity

- 1inch Pathfinder application programming interface, Uniswap V3
  ticks, CoW Swap.
- **Used for**: realised decentralised-exchange-slippage estimation
  feeding the High Quality Liquid Assets Level-2A haircut
  computation.

### E.5 Chainlink, Pyth, Redstone: oracle feeds

- Per-market oracle source as defined in the Morpho Blue market
  parameters.
- **Used for**: historical oracle prices and
  deviation-from-market detection.

---

## F. Stress-event historical data

### F.1 KelpDAO collateral exploit (April 2026)

- Coverage: multiple sources, including post-mortem from the Aave
  governance forum.
- **Used for**: the primary calibration anchor for scenario S5.

### F.2 USDC depeg (March 2023)

- Silicon Valley Bank collapse impact on Circle reserves; USDC traded
  briefly at approximately 0.88 U.S. dollars on secondary markets.
- **Used for**: calibration of scenario S3 (oracle deviation under
  stable depeg).

### F.3 Staked-Ether discount (May 2022)

- Lido staked-Ether traded at a discount to Ether, with an
  approximate 0.94 staked-Ether-to-Ether peak gap.
- **Used for**: calibration of scenario S3 for liquid-staking-token
  collateral types.

### F.4 Mango Markets attack (October 2022): illustrative only

- Oracle-manipulation case study.
- **Used for**: qualitative reference on oracle-attack vectors. Not
  used in calibration.

---

## G. Empirical-finance references

### G.1 Almgren, Chriss (2000): *Optimal execution of portfolio transactions*

- *Journal of Risk*, 2000.
- **Used for**: the power-law impact-cost model used to fit slippage
  curves; the theoretical anchor for the parametric form $\pi(V) = a \cdot V^b$.

### G.2 Frazzini, Israel, Moskowitz (2018): *Trading Costs*

- Working paper (post-publication: *Review of Financial Studies*).
- **Used for**: empirical confirmation that the Almgren, Chriss
  exponent $b$ lies in $[0.50, 0.62]$ across asset classes.
