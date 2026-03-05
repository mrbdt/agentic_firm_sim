from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import yfinance as yf

from firm_sim.tools.cache import TTLCache
from firm_sim.tools.alpaca_rest import AlpacaREST, AlpacaConfig, AlpacaAuthError


@dataclass(slots=True)
class PriceQuote:
    symbol: str
    price: float | None
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "price": self.price, "source": self.source}


class MarketData:
    def __init__(self, *, alpaca: AlpacaREST | None) -> None:
        self.alpaca = alpaca
        self._price_cache = TTLCache(ttl_s=5.0, max_items=512)

    async def get_price(self, symbol: str) -> PriceQuote:
        sym = symbol.upper().strip()
        if not sym:
            return PriceQuote(symbol=symbol, price=None, source="none")
        cached = self._price_cache.get(sym)
        if cached is not None:
            return cached

        # Try Alpaca latest trade first
        if self.alpaca is not None:
            try:
                data = await self.alpaca.data_get(f"/v2/stocks/{sym}/trades/latest")
                trade = data.get("trade") or {}
                p = trade.get("p")
                if isinstance(p, (int, float)):
                    out = PriceQuote(symbol=sym, price=float(p), source="alpaca")
                    self._price_cache.set(sym, out)
                    return out
            except Exception:
                pass

        # Fallback: Yahoo (yfinance)
        def _yf() -> float | None:
            try:
                t = yf.Ticker(sym)
                fi = getattr(t, "fast_info", None)
                if isinstance(fi, dict):
                    lp = fi.get("last_price")
                    if isinstance(lp, (int, float)):
                        return float(lp)
                info = getattr(t, "info", None)
                if isinstance(info, dict):
                    rp = info.get("regularMarketPrice")
                    if isinstance(rp, (int, float)):
                        return float(rp)
            except Exception:
                return None
            return None

        p = await asyncio.to_thread(_yf)
        out = PriceQuote(symbol=sym, price=p, source="yahoo")
        self._price_cache.set(sym, out)
        return out

    async def get_positions(self) -> list[dict[str, Any]]:
        if self.alpaca is None:
            return []
        try:
            positions = await self.alpaca.trading_get("/v2/positions")
            if isinstance(positions, list):
                return positions
        except Exception:
            return []
        return []

    async def get_account(self) -> dict[str, Any] | None:
        if self.alpaca is None:
            return None
        try:
            acct = await self.alpaca.trading_get("/v2/account")
            if isinstance(acct, dict):
                return acct
        except Exception:
            return None
        return None
