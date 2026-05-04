"""GraphQL client for the Morpho Blue subgraph with cursor-based pagination.

We never use offset-based pagination (`skip`) because it is buggy at scale on
The Graph (>5000 results). Instead we paginate by `block_number` + `id`
ordering, which is what The Graph officially recommends.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class SubgraphError(RuntimeError):
    """Raised when the subgraph returns a structured GraphQL error."""


class SubgraphClient:
    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        page_size: int = 1000,
    ) -> None:
        self._url = url
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(timeout=timeout, headers=self._headers)
        self._page_size = page_size

    def __enter__(self) -> "SubgraphClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type((httpx.HTTPError, SubgraphError)),
        reraise=True,
    )
    def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            self._url, json={"query": query, "variables": variables}
        )
        response.raise_for_status()
        body = response.json()
        if "errors" in body and body["errors"]:
            raise SubgraphError(str(body["errors"]))
        return body["data"]

    def paginate(
        self,
        query_template: str,
        entity: str,
        variables: dict[str, Any] | None = None,
        cursor_field: str = "id",
    ) -> Iterator[dict[str, Any]]:
        """Yield entity rows page by page using cursor pagination.

        ``query_template`` must accept ``$first``, ``$cursor``, and any extra
        variables. The query must order by ``cursor_field`` ascending and
        filter ``where: { <cursor_field>_gt: $cursor }``.
        """
        variables = dict(variables or {})
        cursor = ""
        while True:
            variables.update({"first": self._page_size, "cursor": cursor})
            data = self._post(query_template, variables)
            page = data.get(entity, [])
            if not page:
                return
            for row in page:
                yield row
            if len(page) < self._page_size:
                return
            cursor = page[-1][cursor_field]
