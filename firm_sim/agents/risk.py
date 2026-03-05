from __future__ import annotations

from typing import Any

from firm_sim.agents.base import BaseAgent
from firm_sim.bus import Message
from firm_sim.tools.toolbox import ToolContext


def _safe_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


class RiskAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.system_prompt = (
            "You are the Chief Risk Officer at a simulated trading firm.\n"
            "Your job: enforce hard risk limits and clearly communicate approvals/rejections.\n"
            "Hard limits MUST be enforced even if others disagree.\n\n"
            "You approve/reject trade intents from the CEO.\n"
            "Use approve_intent / reject_intent tools.\n"
        )
        self.default_channel = "room:all"
        self.subscribed_channels = [
            "room:all",
            "room:trade_intents",
            "dm:ceo:risk",
        ]
        self.proactive_interval_s = None  # mostly reactive
        self.max_tool_iters = 2
        self.allowed_tools = {
            "send_message",
            "get_price",
            "get_positions",
            "approve_intent",
            "reject_intent",
        }
        self.llm_priority = 2

    async def step(self, inbox: list[Message]) -> None:
        # First, deterministically process any trade intents.
        intents = [
            m
            for m in inbox
            if (m.meta or {}).get("kind") == "trade_intent" and isinstance((m.meta or {}).get("ticket"), dict)
        ]
        if intents:
            ctx = ToolContext(agent_id=self.cfg.id, agent_name=self.cfg.name)
            for m in intents[:5]:
                ticket: dict[str, Any] = dict(m.meta.get("ticket") or {})
                symbol = str(ticket.get("symbol") or "").upper()
                qty = _safe_float(ticket.get("qty")) or 0.0
                side = str(ticket.get("side") or "").lower()

                await self.state.update(
                    self.cfg.id,
                    status="risk_check",
                    current_activity=f"checking {ticket.get('id')} {side} {qty} {symbol}",
                )

                price_q = await self.tools.get_price(ctx, symbol=symbol)
                price = _safe_float(price_q.get("price"))
                if not price or price <= 0:
                    await self.tools.reject_intent(ctx, ticket=ticket, reason=f"Could not fetch reliable price for {symbol}.")
                    continue

                notional = abs(price * qty)

                pos_res = await self.tools.get_positions(ctx)
                gross = 0.0
                for p in (pos_res.get("positions") or []):
                    mv = _safe_float(p.get("market_value"))
                    if mv is None:
                        continue
                    gross += abs(mv)

                max_pos = float(self.risk_limits.get("max_position_usd", 5_000.0))
                max_gross = float(self.risk_limits.get("max_gross_exposure_usd", 20_000.0))

                if notional > max_pos:
                    await self.tools.reject_intent(
                        ctx,
                        ticket=ticket,
                        reason=f"Position notional ${notional:,.0f} exceeds max_position_usd ${max_pos:,.0f}.",
                    )
                    continue

                if (gross + notional) > max_gross:
                    await self.tools.reject_intent(
                        ctx,
                        ticket=ticket,
                        reason=f"Gross exposure would be ${gross+notional:,.0f} > max_gross_exposure_usd ${max_gross:,.0f}.",
                    )
                    continue

                note = f"Price: ${price:.2f} | Notional: ${notional:,.0f} | Current gross: ${gross:,.0f}"
                await self.tools.approve_intent(ctx, ticket=ticket, note=note)

            await self.state.update(self.cfg.id, status="running", current_activity="idle")
            return

        # Otherwise use the normal LLM loop for general comms.
        await super().step(inbox)
