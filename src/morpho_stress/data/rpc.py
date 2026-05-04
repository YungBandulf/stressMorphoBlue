"""Web3 RPC client with retry, fallback, and structured logging.

We deliberately avoid `web3.py`'s built-in retry middleware in favor of an
explicit `tenacity` loop. The middleware retries transparently and would mask
intermittent fallback / outage signals we want to log.
"""

from __future__ import annotations

import logging
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from web3 import HTTPProvider, Web3
from web3.exceptions import Web3RPCError
from web3.types import BlockData

logger = logging.getLogger(__name__)


class RPCClient:
    """Thin wrapper over Web3 with primary + fallback endpoints.

    Use a single instance per pipeline run; stateless beyond connection caching.
    """

    def __init__(
        self,
        rpc_url: str,
        rpc_url_fallback: str | None = None,
        request_timeout: int = 30,
    ) -> None:
        self._primary = self._make_w3(rpc_url, request_timeout)
        self._fallback = (
            self._make_w3(rpc_url_fallback, request_timeout) if rpc_url_fallback else None
        )

    @staticmethod
    def _make_w3(url: str, timeout: int) -> Web3:
        return Web3(HTTPProvider(url, request_kwargs={"timeout": timeout}))

    @property
    def primary(self) -> Web3:
        return self._primary

    # ----- Convenience wrappers with retry + fallback -----

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Web3RPCError, ConnectionError, TimeoutError)),
        reraise=True,
    )
    def get_block(self, block_identifier: int | str = "latest") -> BlockData:
        try:
            return self._primary.eth.get_block(block_identifier)
        except (Web3RPCError, ConnectionError, TimeoutError) as exc:
            if self._fallback is None:
                raise
            logger.warning("primary RPC failed (%s); falling back", exc)
            return self._fallback.eth.get_block(block_identifier)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Web3RPCError, ConnectionError, TimeoutError)),
        reraise=True,
    )
    def call(self, contract_call: Any, block_identifier: int | str = "latest") -> Any:
        """Execute a contract call (e.g. ``contract.functions.foo()``).

        Caller passes the *unbuilt* call object; we apply ``.call(...)``.
        """
        try:
            return contract_call.call(block_identifier=block_identifier)
        except (Web3RPCError, ConnectionError, TimeoutError) as exc:
            if self._fallback is None:
                raise
            logger.warning("primary RPC failed on call (%s); falling back", exc)
            # Rebuild the call against the fallback's contract is non-trivial;
            # for now log and re-raise. Phase 2 will add a contract registry to
            # support proper fallback for arbitrary contract calls.
            raise


def safe_block(latest: int, reorg_buffer: int = 32) -> int:
    """Return the most recent block considered safe from reorgs.

    Ethereum reorg depth in practice is 6–12 blocks; we use 32 for a wide margin.
    """
    return max(0, latest - reorg_buffer)
