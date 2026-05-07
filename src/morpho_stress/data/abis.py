"""Minimal ABIs for the contracts we call in the data acquisition pipeline.

Only the functions/events we actually use are included. The full Morpho Blue
ABI is large; carrying just the slice we need is cleaner and avoids version
drift when Morpho Labs updates their interfaces.

Sources:
- Morpho Blue contract: 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb (mainnet)
  Verified on Etherscan; ABI extracted from there.
- Standard ERC-20: well-known interface.
- Chainlink AggregatorV3Interface: well-known interface.
- Uniswap V3 Quoter (QuoterV2): 0x61fFE014bA17989E743c5F6cB21bF9697530B21e
"""

from __future__ import annotations

# Morpho Blue: just the read functions and CreateMarket event
MORPHO_BLUE_ABI = [
    {
        "inputs": [{"internalType": "Id", "name": "id", "type": "bytes32"}],
        "name": "idToMarketParams",
        "outputs": [
            {"internalType": "address", "name": "loanToken", "type": "address"},
            {"internalType": "address", "name": "collateralToken", "type": "address"},
            {"internalType": "address", "name": "oracle", "type": "address"},
            {"internalType": "address", "name": "irm", "type": "address"},
            {"internalType": "uint256", "name": "lltv", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "Id", "name": "id", "type": "bytes32"}],
        "name": "market",
        "outputs": [
            {"internalType": "uint128", "name": "totalSupplyAssets", "type": "uint128"},
            {"internalType": "uint128", "name": "totalSupplyShares", "type": "uint128"},
            {"internalType": "uint128", "name": "totalBorrowAssets", "type": "uint128"},
            {"internalType": "uint128", "name": "totalBorrowShares", "type": "uint128"},
            {"internalType": "uint128", "name": "lastUpdate", "type": "uint128"},
            {"internalType": "uint128", "name": "fee", "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "Id", "name": "id", "type": "bytes32"},
            {
                "components": [
                    {"internalType": "address", "name": "loanToken", "type": "address"},
                    {"internalType": "address", "name": "collateralToken", "type": "address"},
                    {"internalType": "address", "name": "oracle", "type": "address"},
                    {"internalType": "address", "name": "irm", "type": "address"},
                    {"internalType": "uint256", "name": "lltv", "type": "uint256"},
                ],
                "indexed": False,
                "internalType": "struct MarketParams",
                "name": "marketParams",
                "type": "tuple",
            },
        ],
        "name": "CreateMarket",
        "type": "event",
    },
]


# Standard ERC-20 read-only methods we call
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
]


# Chainlink AggregatorV3Interface
CHAINLINK_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"internalType": "uint80", "name": "roundId", "type": "uint80"},
            {"internalType": "int256", "name": "answer", "type": "int256"},
            {"internalType": "uint256", "name": "startedAt", "type": "uint256"},
            {"internalType": "uint256", "name": "updatedAt", "type": "uint256"},
            {"internalType": "uint80", "name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


# Morpho IOracle interface — every oracle attached to a Morpho Blue market
# implements this. Returns the price of 1 unit of collateral quoted in 1 unit
# of loan asset, scaled by 1e36 + loan_decimals - collateral_decimals.
# This is the canonical interface; works for MorphoChainlinkOracleV2,
# MorphoPythOracle, Redstone wrappers, custom oracles, etc.
# Reference: https://docs.morpho.org/get-started/resources/contracts/oracles/
MORPHO_IORACLE_ABI = [
    {
        "inputs": [],
        "name": "price",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


# Uniswap V3 QuoterV2: quoteExactInputSingle for slippage estimation
UNISWAP_V3_QUOTER_V2_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {
                        "internalType": "uint160",
                        "name": "sqrtPriceLimitX96",
                        "type": "uint160",
                    },
                ],
                "internalType": "struct IQuoterV2.QuoteExactInputSingleParams",
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
            {"internalType": "uint160", "name": "sqrtPriceX96After", "type": "uint160"},
            {"internalType": "uint32", "name": "initializedTicksCrossed", "type": "uint32"},
            {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


# Well-known mainnet addresses
MORPHO_BLUE_MAINNET = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
UNISWAP_V3_QUOTER_V2_MAINNET = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
