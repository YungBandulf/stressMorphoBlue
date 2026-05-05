# Glossary

This document defines every specialised term, mathematical symbol, and
abbreviation used in this repository. Any document that references a term
is expected to either use the full form or to introduce the abbreviation
explicitly on first use, with a back-reference here.

The glossary is organised in three sections: institutional finance terms,
on-chain and protocol-specific terms, and mathematical symbols.

---

## 1. Institutional finance terms

### Basel framework
The set of international banking regulatory standards published by the
Basel Committee on Banking Supervision (the committee, abbreviated as
*Basel Committee* in this repository), hosted at the Bank for
International Settlements. Three iterations exist (Basel I, Basel II,
Basel III); we use Basel III.

### Basel Committee on Banking Supervision
The international standard-setter for banking regulation, hosted at the
Bank for International Settlements in Basel, Switzerland. Publishes
documents under references such as *BCBS 238* (= the 238th publication
of the Basel Committee). When a document is cited as `BCBS NNN` in this
repository, the prefix denotes the publishing committee.

### Liquidity Coverage Ratio
A regulatory ratio defined in BCBS 238 (2013) that requires a regulated
bank to hold enough High Quality Liquid Assets to cover net cash
outflows under a 30-day stress scenario:

$$\text{Liquidity Coverage Ratio} = \frac{\text{High Quality Liquid Assets}}{\text{Net cash outflows over 30 days}} \geq 100\%$$

In this repository, the term **on-chain Liquidity Coverage Ratio** refers
to our adaptation of the same ratio to a Morpho Blue lending market.

### Net Stable Funding Ratio
A complementary regulatory ratio defined in BCBS 295 (2014) that
requires the ratio of *available stable funding* to *required stable
funding* to be at least 100%. Captures medium-term (one-year) liquidity
mismatch, as opposed to the 30-day Liquidity Coverage Ratio.

### High Quality Liquid Assets
Assets that, per Basel III, can be readily converted into cash with
little or no loss in value during a stress scenario. Tiered into three
levels:

- **Level 1**: cash, central-bank reserves, top-rated sovereign debt.
 Haircut: 0%.
- **Level 2A**: highly liquid corporate or covered bonds. Haircut: 15%.
- **Level 2B**: lower-rated corporate or equity. Haircut: 25–50%.

The haircuts represent the assumed loss on monetisation under stress.
Aggregate Level 2 cannot exceed 40% of total High Quality Liquid Assets.

### Available Stable Funding
The portion of a bank's funding sources (equity, deposits, etc.) that is
considered reliable over a one-year horizon. A weighted sum of
liabilities, with weights from BCBS 295 Annex.

### Required Stable Funding
The portion of a bank's assets that requires stable funding over one
year. A weighted sum of assets, with weights from BCBS 295 Annex.

### Stress scenario
A predefined adverse condition (price drop, deposit run, market dislocation)
under which a regulatory ratio is computed. The Basel framework specifies
runoff and inflow factors per asset/liability class for the Liquidity
Coverage Ratio's 30-day stress.

### Confidence interval
A range of values, computed from a sample, that contains the true
parameter with a given probability under a stated statistical model. We
use Wald confidence intervals on regression coefficients (Gaussian
asymptotic approximation).

### Wald confidence interval
A confidence interval of the form $\hat\theta \pm z_{1-\alpha/2}\, \widehat{\text{SE}}(\hat\theta)$, where $\hat\theta$ is the point
estimate, $\widehat{\text{SE}}$ its estimated standard error, and
$z_{1-\alpha/2}$ the standard-normal quantile. Asymptotically valid
under regularity conditions; exact for ordinary least squares
regression coefficients on Gaussian errors.

### Quantile (empirical)
For a sample $\{x_1, \dots, x_n\}$ and a level $q \in [0, 1]$, the
empirical quantile at level $q$ is the value below which a fraction $q$
of observations falls. The 99th-percentile quantile is the value below
which 99% of observations fall.

### Bootstrap (statistical)
A resampling method: draw $n$ values with replacement from a sample to
construct an empirical distribution. We use two variants:

- **Independent and identically distributed bootstrap (i.i.d. bootstrap)**:
 draw each value independently with replacement.
- **Block bootstrap**: draw contiguous blocks of size $k$ to preserve
 short-range autocorrelation in time-series data.

### Monte Carlo simulation
A numerical method that approximates a probability distribution or
expectation by repeated random sampling from a model. Here, we use it
to estimate distributions of bad-debt outcomes under random shocks.

### Falsifiable hypothesis
A scientific claim formulated such that observations could contradict
it. We adopt this standard from Popperian methodology: the framework's
output must include criteria whose violation by the data would refute
the claim.

---

## 2. On-chain and protocol-specific terms

### Morpho Blue
A non-custodial lending protocol, deployed on Ethereum and other chains,
in which each lending market is an **isolated** pair of (collateral
asset, loan asset) with immutable parameters. Implemented in roughly
650 lines of Solidity. Reference: Morpho Labs, *Morpho Blue Whitepaper*.

### Lending market
In Morpho Blue terminology, an immutable tuple
(loan asset, collateral asset, oracle, interest rate model, liquidation
loan-to-value threshold) defining one isolated market. Different markets
do not share liquidity or risk.

### Collateral asset
The asset a borrower pledges. Must be locked in the protocol while the
borrow is active.

### Loan asset
The asset a borrower receives and a supplier deposits. Interest accrues
in this asset.

### Supplier
A user who deposits the loan asset to earn interest.

### Borrower
A user who pledges collateral and withdraws the loan asset, paying
interest on the borrowed amount.

### Liquidator
A third-party actor who repays a borrower's debt in exchange for the
borrower's collateral plus a bonus, when the borrower's collateralisation
falls below the market's threshold.

### Loan-to-value (per position)
The ratio of a borrower's debt to the value of their collateral, both
denominated in the loan asset:

$$\text{Loan-to-value}_i = \frac{b_i}{c_i \cdot P}$$

where $b_i$ is the borrower's debt in loan-asset units, $c_i$ is the
collateral in collateral-asset units, and $P$ is the oracle-reported
price of one collateral unit in loan-asset units.

### Liquidation loan-to-value threshold
The market parameter, fixed at market creation, above which a position
becomes liquidatable. Denoted $\Lambda$ in our formulas. Typical values:
86% for major asset/stablecoin pairs, 91.5% for stable/stable pairs.

### Liquidation incentive factor
The multiplier applied to a borrower's debt when seizing collateral, in
favour of the liquidator. Morpho Blue formula:

$$\text{Liquidation incentive factor} = \min\Bigl(1.15, \frac{1}{0.3 \cdot \Lambda + 0.7}\Bigr)$$

For $\Lambda = 0.86$, the factor is approximately $1.043$ (4.3% bonus).
The cap at $1.15$ ensures the bonus does not grow unboundedly for
markets with low $\Lambda$.

### Interest rate model
A function mapping the market utilisation (fraction of supply that is
borrowed) to a borrow rate. Morpho Blue uses an *adaptive curve* model
described below.

### Adaptive curve interest rate model
The canonical Morpho Blue interest rate model. Two layers:

- **Curve layer**: piecewise function of utilisation $U$, passing
 through a parameter `rate_at_target` at $U = U_{\text{target}}$ (the
 target utilisation, a market parameter, typically 90%).
- **Adaptive layer**: `rate_at_target` itself drifts over time as a
 function of the deviation between observed and target utilisation,
 bounded by `min_rate_at_target` and `max_rate_at_target`.

### Utilisation
The ratio of borrowed loan asset to supplied loan asset:

$$U = \frac{B}{S} \,\in\, [0, 1]$$

where $B$ is total borrowed and $S$ is total supplied. A market at
$U = 1$ is fully utilised: no liquidity is available for new borrows or
withdrawals.

### Oracle (price oracle)
A contract that reports the price of the collateral asset in loan-asset
units. Different price-discovery mechanisms exist; we model two:

- **Exogenous oracle** (e.g., Chainlink, Pyth, Redstone): reports an
 off-chain price aggregated independently of any on-chain swap. Liquidator
 selling does not affect the oracle's reading.
- **Time-Weighted Average Price oracle from a decentralised exchange**
 (e.g., Uniswap V3): reports the geometric mean of recent on-chain
 trade prices over a window. Liquidator selling moves the underlying
 exchange price, which propagates into the oracle through the time
 average.

### Time-Weighted Average Price
The price obtained by averaging instantaneous prices over a time window,
weighted by the duration each price was active. In Uniswap V3, the
average is computed in *tick* space (logarithmic), so the resulting
price is a geometric mean rather than an arithmetic one.

### Tick (Uniswap V3)
A discretisation of price into integer indices, with $\text{price} = 1.0001^{\text{tick}}$. Uniswap V3 stores cumulative ticks across blocks;
the time-weighted average tick over a window divided by window length
yields the geometric-mean price.

### Decentralised exchange
A non-custodial venue for trading tokens on-chain. We use Uniswap V3 as
the canonical example for both price discovery and liquidation execution.

### Slippage
The difference between an oracle-quoted price and the realised execution
price for a trade of given size:

$$\text{slippage}(V) = \frac{P_{\text{oracle}} - P_{\text{realised}}(V)}{P_{\text{oracle}}}$$

Slippage grows with trade size $V$. In this repository we model it as a
power law (see *Almgren–Chriss model* below).

### Almgren–Chriss model
The empirical impact-cost model from Almgren and Chriss (2000), which
expresses execution slippage as a power function of trade size:

$$\pi(V) = a \cdot V^b$$

with parameters $a > 0$ and $b \in (0, 1)$ fitted from data. Originally
introduced for equity markets; later confirmed to apply broadly across
asset classes (Frazzini, Israel & Moskowitz, 2018).

### Total Value Locked
The aggregate value of assets deposited in a protocol or market,
typically denominated in dollars. A standard size metric in
decentralised-finance reporting.

### Bad debt
Loan asset owed to suppliers but not recoverable through liquidation:

$$\text{bad debt} = \max\bigl(0, \text{debt repaid} - \text{realised value of seized collateral}\bigr)$$

Bad debt is ultimately absorbed by the supplier pool (through a
proportional reduction of supplier balances).

### Maximal Extractable Value
The profit a transaction orderer (validator or block builder) can
extract by including, excluding, or reordering transactions in a block.
Liquidations are a primary source of extractable value; under stress,
gas-price competition can leave some liquidations unprofitable for the
intended liquidator.

### MetaMorpho vault
A non-custodial vault contract built on top of Morpho Blue, in which a
**curator** (a third-party risk manager) allocates supplier deposits
across one or more Morpho Blue lending markets according to a stated
strategy and risk constraints.

### Curator
The party that operates a MetaMorpho vault: chooses which Morpho Blue
markets are eligible, sets per-market caps, and rebalances allocations.
Curators include institutional risk-management firms (Steakhouse
Financial, Block Analitica, B.Protocol, others).

### Reorg (chain reorganisation)
A revert of one or more recent blocks on a blockchain, replaced by a
different fork. On Ethereum post-merge, reorgs of more than a few blocks
are rare but possible. We use a 32-block buffer when reading state via
remote procedure calls.

### Remote procedure call (RPC)
The protocol used to communicate with a blockchain node from off-chain
software. We use it for direct state queries (`eth_call`,
`eth_getBlock`, etc.). Providers include Alchemy, Llama RPC, Infura.

### Subgraph
An indexer (typically deployed via The Graph protocol) that serves
queriable, structured data derived from blockchain events. Used as a
secondary source for events (Supply, Withdraw, Borrow, Liquidate).

---

## 3. Mathematical symbols and conventions

### State vector

For a Morpho Blue lending market $M$ at block $t$, we use:

| Symbol | Definition |
|---|---|
| $S_t$ | Total supply (loan asset units), denoted `total_supply_assets` on-chain |
| $B_t$ | Total borrow (loan asset units), denoted `total_borrow_assets` on-chain |
| $L_t = S_t - B_t$ | Available liquidity (loan asset units) |
| $U_t = B_t / S_t$ | Utilisation $\in [0, 1]$ |
| $C_t$ | Aggregate collateral pool (collateral asset units) |
| $P_t$ | Oracle price of one collateral unit, in loan-asset units |
| $\Lambda$ | Liquidation loan-to-value threshold (market parameter, $\in [0, 1]$) |
| $b_i, c_i$ | Borrower $i$'s debt (loan asset) and collateral (collateral asset) |
| $\pi(V)$ | Slippage of a trade of size $V$ collateral units, $\in [0, 1]$ |

### Stress scenario notation

A stress scenario is a quadruple $(\delta, T, h, \rho)$:

| Symbol | Definition |
|---|---|
| $\delta$ | Shock function applied to the state at $t$ |
| $T$ | Shock duration in blocks |
| $h$ | Observation horizon in blocks (with $h \geq T$) |
| $\rho$ | Behavioural and dynamic rule from $t$ to $t + h$ |

### Specific scenario parameters

| Symbol | Definition | Used in |
|---|---|---|
| $\alpha$ | Fraction of total supply withdrawn under stress | S1 (withdrawal run) |
| $\beta$ | Fraction of total supply added as new borrow | S2 (utilisation spike) |
| $\Delta$ | Total fractional drawdown of collateral price | S3, S4 |
| $\Delta t$ | Window over which the drawdown unfolds | S3, S4 |
| $\lambda$ | Time-Weighted Average Price window in blocks | Oracle smoothing |

### Time and block conventions

- Block time on Ethereum (post-merge): 12 seconds, denoted
 $\Delta_{\text{block}} = 12$.
- One year is $365 \times 24 \times 3600 = 31{,}536{,}000$ seconds.
- All timestamps are reported in Coordinated Universal Time (UTC).

### Numerical conventions

- All rates are continuously compounded annual rates (annualised in base
 $e$); a value of $0.04$ means 4% annualised.
- All prices are floating-point numbers; we do not replicate the
 contract's fixed-point WAD arithmetic except where explicitly stated,
 since stress-test outcomes are insensitive to the eighteenth decimal.
- A small numerical tolerance $\varepsilon = 10^{-9}$ is used to avoid
 division-by-zero artefacts.

---

## 4. Document references

- BCBS 238: BCBS, *Basel III: The Liquidity Coverage Ratio and liquidity risk monitoring tools*, January 2013.
- BCBS 295: BCBS, *Basel III: The Net Stable Funding Ratio*, October 2014.
- BCBS 144: BCBS, *Principles for Sound Liquidity Risk Management and Supervision*, September 2008.
- Almgren, R., Chriss, N. (2000), *Optimal execution of portfolio transactions*, Journal of Risk.
- Frazzini, A., Israel, R., Moskowitz, T. (2018), *Trading Costs*, working paper.
- Chiu, J., Ozdenoren, E., Yuan, K., Zhang, S. (2023), *On the inherent fragility of decentralised-finance lending*, Bank for International Settlements Working Paper 1062.
- Gudgeon, L., Werner, S. M., Perez, D., Knottenbelt, W. J. (2020), *Decentralised-finance protocols for loanable funds*, Financial Cryptography 2020.
- Morpho Labs, *Morpho Blue Whitepaper* and *Morpho Blue Yellow Paper*.
