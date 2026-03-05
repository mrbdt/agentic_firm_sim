from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class AlpacaAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class AlpacaConfig:
    key_id: str | None
    secret_key: str | None
    base_url: str
    data_url: str


class AlpacaREST:
    def __init__(self, cfg: AlpacaConfig) -> None:
        self.cfg = cfg
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        if not self.cfg.key_id or not self.cfg.secret_key:
            raise AlpacaAuthError("Missing Alpaca credentials (ALPACA_KEY_ID / ALPACA_SECRET_KEY).")
        return {
            "APCA-API-KEY-ID": self.cfg.key_id,
            "APCA-API-SECRET-KEY": self.cfg.secret_key,
        }

    async def trading_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self.cfg.base_url.rstrip("/") + path
        r = await self._client.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json()

    async def trading_post(self, path: str, payload: dict[str, Any]) -> Any:
        url = self.cfg.base_url.rstrip("/") + path
        r = await self._client.post(url, headers=self._headers(), json=payload)
        r.raise_for_status()
        return r.json()

    async def data_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self.cfg.data_url.rstrip("/") + path
        r = await self._client.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json()
