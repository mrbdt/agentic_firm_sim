from __future__ import annotations

from firm_sim.agents.base import BaseAgent


class PMAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.system_prompt = (
            "You are a Portfolio Manager at a simulated trading firm.\n"
            "Your job: translate research + live prices into concrete trade proposals.\n"
            "You must be selective and risk-aware.\n\n"
            "When proposing a trade, use propose_trade with:\n"
            "- symbol, side, qty\n"
            "- 1-3 sentence rationale\n"
            "- confidence (0-1)\n"
            "- horizon\n"
            "- optional stop_loss_pct / take_profit_pct\n"
            "- sources (URLs) if you relied on web info\n\n"
            "Do NOT send trade intents directly to risk; proposals go to the CEO.\n"
        )
        self.default_channel = "room:all"
        self.subscribed_channels = [
            "room:all",
            "room:research",
            "room:trade_ideas",
            "dm:ceo:pm",
        ]
        self.proactive_interval_s = 180.0  # every 3 minutes try to find 1 good idea
        self.max_tool_iters = 4
        self.allowed_tools = {
            "send_message",
            "web_search",
            "web_open",
            "get_price",
            "get_positions",
            "propose_trade",
        }
        self.llm_priority = 5
