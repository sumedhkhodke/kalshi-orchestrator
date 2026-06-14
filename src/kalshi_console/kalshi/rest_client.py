# src/kalshi_console/kalshi/rest_client.py
"""Minimal signed async REST client. Grows into the full gateway in M1."""
from __future__ import annotations

from typing import Any

import httpx

from kalshi_console.kalshi.endpoints import REST_PREFIX, Hosts
from kalshi_console.kalshi.signing import Signer


class KalshiRestClient:
    def __init__(
        self,
        hosts: Hosts,
        signer: Signer | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._hosts = hosts
        self._signer = signer
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def get(
        self, path: str, *, auth: bool = False, params: dict[str, Any] | None = None
    ) -> Any:
        """GET `path` (relative to the /trade-api/v2 base). Query params are excluded from signing."""
        url = f"{self._hosts.rest_base}{path}"
        headers: dict[str, str] = {}
        if auth:
            if self._signer is None:
                raise RuntimeError("auth required but no signer configured")
            headers = self._signer.headers("GET", f"{REST_PREFIX}{path}")
        resp = await self._client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "KalshiRestClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
