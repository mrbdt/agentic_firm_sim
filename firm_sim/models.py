from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass(slots=True)
class TradeTicket:
    id: str
    created_ts: float

    symbol: str
    side: str  # buy/sell
    qty: float
    order_type: str = "market"
    time_in_force: str = "day"

    horizon: str = "days"
    confidence: float = 0.5
    rationale: str = ""
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    sources: list[str] | None = None

    @staticmethod
    def create(
        symbol: str,
        side: str,
        qty: float,
        *,
        order_type: str = "market",
        time_in_force: str = "day",
        horizon: str = "days",
        confidence: float = 0.5,
        rationale: str = "",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        sources: list[str] | None = None,
    ) -> "TradeTicket":
        return TradeTicket(
            id=new_id("tt"),
            created_ts=time.time(),
            symbol=symbol.upper(),
            side=side.lower(),
            qty=float(qty),
            order_type=order_type,
            time_in_force=time_in_force,
            horizon=horizon,
            confidence=float(confidence),
            rationale=rationale,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            sources=sources or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
