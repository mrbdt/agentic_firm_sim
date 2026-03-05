from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from firm_sim.tools.alpaca_rest import AlpacaREST


@dataclass(slots=True)
class OrderResult:
    ok: bool
    broker_order_id: str | None
    status: str
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "broker_order_id": self.broker_order_id,
            "status": self.status,
            "raw": self.raw or {},
        }


class Broker:
    """Order execution abstraction.

    Currently supports Alpaca stocks/crypto via REST (paper or live depending on ALPACA_BASE_URL).
    """

    def __init__(self, alpaca: AlpacaREST | None) -> None:
        self.alpaca = alpaca

    async def place_market_order(self, symbol: str, side: str, qty: float, *, time_in_force: str = "day") -> OrderResult:
        if self.alpaca is None:
            return OrderResult(ok=False, broker_order_id=None, status="no_broker", raw=None)

        payload: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.lower(),
            "type": "market",
            "time_in_force": time_in_force,
            "qty": str(qty),
        }
        try:
            data = await self.alpaca.trading_post("/v2/orders", payload)
            oid = data.get("id")
            status = data.get("status", "submitted")
            return OrderResult(ok=True, broker_order_id=str(oid) if oid else None, status=str(status), raw=data)
        except Exception as e:
            return OrderResult(ok=False, broker_order_id=None, status=f"error:{e}", raw=None)
