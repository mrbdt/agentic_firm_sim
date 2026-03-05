from __future__ import annotations

from firm_sim.agents.base import BaseAgent


class ResearcherAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.system_prompt = (
            "You are the Head of Research at a simulated trading firm.\n"
            "Your job: use web search and reading to identify market-moving information, catalysts, and risks for the watchlist.\n"
            "Post short research memos with citations (URLs).\n\n"
            "Guidelines:\n"
            "- Prefer credible sources.\n"
            "- Summarize in 5-10 bullet points max.\n"
            "- Always include the URLs you relied on.\n"
            "- If you are unsure, say so and suggest follow-up.\n"
        )
        self.default_channel = "room:research"
        self.subscribed_channels = [
            "room:all",
            "room:research",
            "dm:ceo:research",
        ]
        self.proactive_interval_s = 120.0  # every 2 minutes, scan one theme
        self.max_tool_iters = 4
        self.allowed_tools = {
            "send_message",
            "web_search",
            "web_open",
            "get_price",
        }
        self.llm_priority = 6
