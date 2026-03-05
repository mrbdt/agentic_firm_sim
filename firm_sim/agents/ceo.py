from __future__ import annotations

from firm_sim.agents.base import BaseAgent


class CEOAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.system_prompt = (
            "You are the CEO of a simulated trading firm.\n"
            "Your job: (1) answer the Chairman quickly, (2) coordinate employees, (3) decide which trade proposals become trade intents,\n"
            "and (4) maintain a coherent risk posture.\n\n"
            "Communication style: concise, decisive, no fluff.\n"
            "If you receive a high-priority message from the Chairman, respond immediately in <=8 lines and delegate follow-ups.\n"
            "When responding to the Chairman, post your reply to **room:chairman** (so they see it).\n"
            "When you choose to advance a trade proposal into an intent, prefer using submit_intent_from_message with the proposal's message_id.\n"
            "Do NOT place orders yourself.\n"
        )
        self.default_channel = "room:all"
        self.subscribed_channels = [
            "room:all",
            "room:trade_ideas",
            "room:trade_executed",
            "room:ops",
            "room:chairman",
            "dm:pm:ceo",
            "dm:risk:ceo",
            "dm:chairman:ceo",
            "dm:exec:ceo",
        ]
        self.proactive_interval_s = 15.0  # light coordination loop
        self.max_tool_iters = 3
        self.allowed_tools = {
            "send_message",
            "get_message",
            "web_search",
            "web_open",
            "get_price",
            "get_positions",
            "submit_intent",
            "submit_intent_from_message",
        }
        # High priority (Chairman-facing)
        self.llm_priority = 1
