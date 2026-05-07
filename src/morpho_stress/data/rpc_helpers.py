"""RPC helpers shared across data acquisition scripts.

Provides three operations that several scripts need:

1. `get_erc20_metadata(rpc, address)` — fetch (symbol, decimals) for any ERC-20.
2. `get_block_timestamp(rpc, block_number)` — fetch the wall-clock time of a block.
3. `detect_oracle_type(rpc, oracle_address)` — categorise the oracle source by
   inspecting its interface. Returns one of {chainlink, pyth, redstone,
   uniswap_twap, composite, unknown}.

All three are network-light (single RPC call each), use checksum addresses,
and tolerate partial failures (return sensible defaults rather than raise).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from web3 import Web3
from web3.exceptions import ContractLogicError, Web3RPCError

from morpho_stress.data.abis import CHAINLINK_ABI, ERC20_ABI
from morpho_stress.data.rpc import RPCClient

logger = logging.getLogger(__name__)


def to_checksum(addr: str) -> str:
    """Convert an address to its EIP-55 checksum form (lowercase 0x...)."""
    return Web3.to_checksum_address(addr)


def get_erc20_metadata(rpc: RPCClient, address: str) -> tuple[str, int]:
    """Read (symbol, decimals) from an ERC-20 contract.

    Returns ("UNKNOWN", 18) if the contract doesn't expose these (some
    older non-standard tokens). Decimals defaults to 18 because that's the
    EVM convention.
    """
    addr = to_checksum(address)
    contract = rpc.primary.eth.contract(address=addr, abi=ERC20_ABI)

    try:
        symbol = contract.functions.symbol().call()
    except (ContractLogicError, Web3RPCError, ValueError) as e:
        logger.warning("Failed to read symbol for %s: %s", address, e)
        symbol = "UNKNOWN"

    try:
        decimals = int(contract.functions.decimals().call())
    except (ContractLogicError, Web3RPCError, ValueError) as e:
        logger.warning("Failed to read decimals for %s: %s — defaulting to 18", address, e)
        decimals = 18

    # Some non-standard tokens return symbol as bytes32 rather than string;
    # web3.py decodes to str if abi says string, but if it fails, we get
    # an exception above. So `symbol` is str at this point.
    return str(symbol), decimals


def get_block_timestamp(rpc: RPCClient, block_number: int) -> datetime:
    """Return the timestamp of a given block as a tz-aware UTC datetime."""
    block = rpc.get_block(block_number)
    ts = int(block["timestamp"])
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def detect_oracle_type(rpc: RPCClient, oracle_address: str) -> str:
    """Classify an oracle by best-effort interface probing.

    Heuristic:
        - If `price()` succeeds → "morpho_oracle" (the canonical Morpho Blue
          oracle interface; every oracle attached to a Morpho market exposes
          it, regardless of underlying source — Chainlink, Pyth, Redstone,
          custom).
        - Else if address is the zero address → "none" (idle markets).
        - Else "unknown" — caller should investigate.

    We do not distinguish the underlying feed source (Chainlink vs. Pyth
    vs. custom) because that distinction does not affect our framework —
    the oracle is always queried via `price()` and treated as a black box
    feed. If a downstream consumer needs to know the underlying source,
    they can read the implementation-specific fields (BASE_FEED_1, etc.).
    """
    if oracle_address.lower() in ("0x0000000000000000000000000000000000000000", "0x"):
        return "none"

    addr = to_checksum(oracle_address)

    # Try Morpho IOracle interface (covers all oracle types attached to
    # Morpho Blue markets: Chainlink wrappers, Pyth wrappers, custom).
    try:
        from morpho_stress.data.abis import MORPHO_IORACLE_ABI
        contract = rpc.primary.eth.contract(address=addr, abi=MORPHO_IORACLE_ABI)
        contract.functions.price().call()
        return "morpho_oracle"
    except (ContractLogicError, Web3RPCError, ValueError) as e:
        logger.debug("Oracle %s does not implement IOracle.price(): %s", oracle_address, e)

    return "unknown"


def normalize_address(address: str) -> str:
    """Lowercase, 0x-prefixed canonical form for storage."""
    if not address.startswith("0x"):
        address = "0x" + address
    return address.lower()
