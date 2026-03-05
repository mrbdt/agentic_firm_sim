from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

import orjson

from firm_sim.bus.models import Message
from firm_sim.models import TradeTicket
from firm_sim.tools.web_tools import WebTools
from firm_sim.tools.market_data import MarketData
from firm_sim.tools.broker import Broker


@dataclass(slots=True)
class ToolContext:
    agent_id: str
    agent_name: str


class ToolBox:
    """Shared tools available to agents.

    Messages between agents are natural language, but tools provide deterministic interfaces.
    """

    def __init__(self, *, bus, web: WebTools, market: MarketData, broker: Broker) -> None:
        self.bus = bus
        self.web = web
        self.market = market
        self.broker = broker

    # --- Communication ---

    async def send_message(
        self,
        ctx: ToolContext,
        *,
        channel: str,
        content: str,
        priority: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        msg = Message.create(channel=channel, sender=ctx.agent_id, content=content, priority=priority, meta=meta or {})
        self.bus.publish(msg)
        return {"ok": True, "message_id": msg.id}

    async def get_message(self, ctx: ToolContext, *, message_id: str) -> dict[str, Any]:
        m = self.bus.get_by_id(message_id)
        if not m:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "message": m.to_dict()}

    # --- Web ---

    async def web_search(self, ctx: ToolContext, *, query: str, max_results: int = 5) -> dict[str, Any]:
        results = await self.web.search(query, max_results=max_results)
        return {"ok": True, "query": query, "results": results}

    async def web_open(self, ctx: ToolContext, *, url: str, max_chars: int = 8000) -> dict[str, Any]:
        doc = await self.web.open_url(url, max_chars=max_chars)
        return {"ok": True, "url": doc.get("url"), "text": doc.get("text", "")}

    # --- Market ---

    async def get_price(self, ctx: ToolContext, *, symbol: str) -> dict[str, Any]:
        q = await self.market.get_price(symbol)
        return {"ok": True, **q.to_dict()}

    async def get_positions(self, ctx: ToolContext) -> dict[str, Any]:
        pos = await self.market.get_positions()
        return {"ok": True, "positions": pos}

    # --- Trade flow ---

    async def propose_trade(
        self,
        ctx: ToolContext,
        *,
        symbol: str,
        side: str,
        qty: float,
        rationale: str,
        confidence: float = 0.5,
        horizon: str = "days",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        sources: list[str] | None = None,
    ) -> dict[str, Any]:
        tt = TradeTicket.create(
            symbol=symbol,
            side=side,
            qty=qty,
            rationale=rationale,
            confidence=confidence,
            horizon=horizon,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            sources=sources or [],
        )
        content = (
            f"Trade proposal ({tt.id}): {tt.side.upper()} {tt.qty} {tt.symbol}\n"
            f"Horizon: {tt.horizon} | Confidence: {tt.confidence:.2f}\n"
            f"Rationale: {tt.rationale}"
        )
        meta = {"ticket": tt.to_dict(), "kind": "trade_proposal"}

        # Broadcast in the trade ideas room and DM the CEO.
        self.bus.publish(Message.create(channel="room:trade_ideas", sender=ctx.agent_id, content=content, meta=meta))
        self.bus.publish(Message.create(channel="dm:pm:ceo", sender=ctx.agent_id, content=content, meta=meta))
        return {"ok": True, "ticket": tt.to_dict()}

    async def submit_intent(self, ctx: ToolContext, *, ticket: dict[str, Any], note: str = "") -> dict[str, Any]:
        # CEO -> Risk
        meta = {"ticket": ticket, "kind": "trade_intent"}
        content = f"Trade intent: {ticket.get('id')}\n{note}".strip()
        self.bus.publish(Message.create(channel="room:trade_intents", sender=ctx.agent_id, content=content, meta=meta))
        self.bus.publish(Message.create(channel="dm:ceo:risk", sender=ctx.agent_id, content=content, meta=meta))
        return {"ok": True}

    async def submit_intent_from_message(self, ctx: ToolContext, *, message_id: str, note: str = "") -> dict[str, Any]:
        m = self.bus.get_by_id(message_id)
        if not m:
            return {"ok": False, "error": "message_not_found"}
        ticket = (m.meta or {}).get("ticket")
        if not isinstance(ticket, dict):
            return {"ok": False, "error": "no_ticket_in_message"}
        return await self.submit_intent(ctx, ticket=ticket, note=note)

    async def approve_intent(self, ctx: ToolContext, *, ticket: dict[str, Any], note: str = "") -> dict[str, Any]:
        meta = {"ticket": ticket, "kind": "trade_approved"}
        content = f"APPROVED: {ticket.get('id')}\n{note}".strip()
        self.bus.publish(Message.create(channel="room:trade_approved", sender=ctx.agent_id, content=content, meta=meta))
        self.bus.publish(Message.create(channel="dm:risk:exec", sender=ctx.agent_id, content=content, meta=meta))
        return {"ok": True}

    async def reject_intent(self, ctx: ToolContext, *, ticket: dict[str, Any], reason: str) -> dict[str, Any]:
        meta = {"ticket": ticket, "kind": "trade_rejected"}
        content = f"REJECTED: {ticket.get('id')}\nReason: {reason}".strip()
        self.bus.publish(Message.create(channel="room:trade_rejected", sender=ctx.agent_id, content=content, meta=meta))
        self.bus.publish(Message.create(channel="dm:risk:ceo", sender=ctx.agent_id, content=content, meta=meta))
        return {"ok": True}

    # --- Execution ---

    async def place_order(self, ctx: ToolContext, *, symbol: str, side: str, qty: float, time_in_force: str = "day") -> dict[str, Any]:
        res = await self.broker.place_market_order(symbol, side, qty, time_in_force=time_in_force)
        return {"ok": res.ok, **res.to_dict()}

    async def dispatch(self, ctx: ToolContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn_map: dict[str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]] = {
            "send_message": self.send_message,
            "get_message": self.get_message,
            "web_search": self.web_search,
            "web_open": self.web_open,
            "get_price": self.get_price,
            "get_positions": self.get_positions,
            "propose_trade": self.propose_trade,
            "submit_intent": self.submit_intent,
            "submit_intent_from_message": self.submit_intent_from_message,
            "approve_intent": self.approve_intent,
            "reject_intent": self.reject_intent,
            "place_order": self.place_order,
        }
        fn = fn_map.get(name)
        if not fn:
            return {"ok": False, "error": f"unknown_tool:{name}"}
        try:
            return await fn(ctx, **args)
        except Exception as e:
            return {"ok": False, "error": f"tool_error:{name}:{e}"}
