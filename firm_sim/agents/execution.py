from __future__ import annotations

from typing import Any

from firm_sim.agents.base import BaseAgent
from firm_sim.bus import Message
from firm_sim.tools.toolbox import ToolContext


class ExecutionAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.system_prompt = (
            "You are Head of Execution at a simulated trading firm.\n"
            "Your job: execute approved trade intents efficiently and report outcomes.\n"
            "Only you may place orders.\n"
            "When you receive an approved intent, place a market order via place_order and report the broker id + status.\n"
        )
        self.default_channel = "room:all"
        self.subscribed_channels = [
            "room:all",
            "room:trade_approved",
            "dm:risk:exec",
        ]
        self.proactive_interval_s = None
        self.max_tool_iters = 1
        self.allowed_tools = {
            "send_message",
            "get_price",
            "get_positions",
            "place_order",
        }
        self.llm_priority = 2
        self._done: set[str] = set()

    async def step(self, inbox: list[Message]) -> None:
        approvals = [
            m
            for m in inbox
            if (m.meta or {}).get("kind") == "trade_approved" and isinstance((m.meta or {}).get("ticket"), dict)
        ]
        if approvals:
            ctx = ToolContext(agent_id=self.cfg.id, agent_name=self.cfg.name)
            for m in approvals[:5]:
                ticket: dict[str, Any] = dict(m.meta.get("ticket") or {})
                tid = str(ticket.get("id") or "")
                if tid and tid in self._done:
                    continue
                symbol = str(ticket.get("symbol") or "").upper()
                side = str(ticket.get("side") or "").lower()
                qty = float(ticket.get("qty") or 0.0)
                tif = str(ticket.get("time_in_force") or "day")

                await self.state.update(
                    self.cfg.id,
                    status="executing",
                    current_activity=f"placing order for {tid} {side} {qty} {symbol}",
                )
                res = await self.tools.place_order(ctx, symbol=symbol, side=side, qty=qty, time_in_force=tif)

                content = (
                    f"EXECUTED {tid}: {side.upper()} {qty} {symbol}\n"
                    f"Result: ok={res.get('ok')} status={res.get('status')} broker_order_id={res.get('broker_order_id')}"
                )
                meta = {"ticket": ticket, "order": res, "kind": "trade_executed"}
                self.bus.publish(Message.create(channel="room:trade_executed", sender=self.cfg.id, content=content, meta=meta))
                self.bus.publish(Message.create(channel="dm:exec:ceo", sender=self.cfg.id, content=content, meta=meta))

                if tid:
                    self._done.add(tid)

            await self.state.update(self.cfg.id, status="running", current_activity="idle")
            return

        await super().step(inbox)
