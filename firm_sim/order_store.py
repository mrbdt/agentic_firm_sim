from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OrderRow:
    id: str
    ts: float
    symbol: str
    side: str
    qty: float
    order_type: str
    status: str
    broker_order_id: str | None
    meta_json: str | None
