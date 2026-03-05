from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import orjson

from firm_sim.bus import Message, MessageBus
from firm_sim.state import StateStore
from firm_sim.tools import OllamaClient, ToolBox, ToolContext
from firm_sim.agents.parsing import parse_agent_output


@dataclass(slots=True)
class AgentConfig:
    id: str
    name: str
    title: str
    role: str
    model: str
    heartbeat_seconds: float = 5.0
    can_trade: bool = False


def _truncate(s: str, n: int = 600) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    return s[:n] + "…"


class BaseAgent:
    def __init__(
        self,
        cfg: AgentConfig,
        *,
        bus: MessageBus,
        state: StateStore,
        llm: OllamaClient,
        tools: ToolBox,
        watchlist: list[str] | None = None,
        risk_limits: dict[str, Any] | None = None,
    ) -> None:
        self.cfg = cfg
        self.bus = bus
        self.state = state
        self.llm = llm
        self.tools = tools
        self.watchlist = watchlist or []
        self.risk_limits = risk_limits or {}

        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

        self._sub = None
        self._history: list[dict[str, str]] = []  # short rolling LLM history
        self._last_proactive_ts: float = 0.0

        # role-specific defaults (overridden by subclasses)
        self.system_prompt = "You are an employee."
        self.default_channel = "room:all"
        self.subscribed_channels: list[str] = ["room:all"]
        self.proactive_interval_s: float | None = None
        self.max_tool_iters: int = 4
        self.allowed_tools: set[str] = set()

        # LLM scheduling: lower is higher priority
        self.llm_priority: int = 5

    async def start(self) -> None:
        from firm_sim.state import AgentState

        await self.state.register(
            AgentState(
                agent_id=self.cfg.id,
                name=self.cfg.name,
                title=self.cfg.title,
                role=self.cfg.role,
                status="running",
                current_objective="boot",
                current_activity="starting up",
            )
        )
        self._sub = self.bus.subscribe(self.subscribed_channels, max_queue=2000)
        self._task = asyncio.create_task(self.run_loop(), name=f"agent:{self.cfg.id}")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._sub:
            self._sub.close()
            self._sub = None

    async def run_loop(self) -> None:
        await self.state.update(self.cfg.id, current_objective="operate", current_activity="idle")
        while not self._stop.is_set():
            t0 = time.time()
            try:
                inbox = self._drain_inbox(max_items=20)
                await self.state.update(self.cfg.id, inbox_depth=len(inbox))

                should_act = bool(inbox)
                if not should_act and self.proactive_interval_s is not None:
                    if (time.time() - self._last_proactive_ts) >= self.proactive_interval_s:
                        should_act = True

                if should_act:
                    await self.step(inbox)
                    if not inbox:
                        self._last_proactive_ts = time.time()
                else:
                    await self.state.update(self.cfg.id, status="idle", current_activity="waiting for messages")

            except Exception as e:
                await self.state.update(self.cfg.id, status="error", last_error=str(e), current_activity="error")
                self.bus.publish(Message.create(channel="room:ops", sender=self.cfg.id, content=f"Agent error: {e}"))

            elapsed = time.time() - t0
            sleep_s = max(0.0, float(self.cfg.heartbeat_seconds) - elapsed)
            await asyncio.sleep(sleep_s)

    def _drain_inbox(self, max_items: int = 20) -> list[Message]:
        if not self._sub:
            return []
        q = self._sub.queue
        items: list[Message] = []
        for _ in range(max_items):
            try:
                items.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break
        items.sort(key=lambda m: (-m.priority, m.ts))
        return items

    def _build_inbox_digest(self, inbox: list[Message]) -> str:
        if not inbox:
            return "(no new messages)"
        parts: list[str] = []
        for m in inbox[-12:]:
            kind = ""
            try:
                k = (m.meta or {}).get("kind")
                if isinstance(k, str) and k:
                    kind = f" kind={k}"
            except Exception:
                kind = ""
            pr = "HIGH" if m.priority >= 10 else "normal"
            parts.append(f"[{m.channel}] id={m.id} pr={pr}{kind} | {m.sender}: {_truncate(m.content, 400)}")
        return "\n".join(parts)

    def _tool_instructions(self) -> str:
        tools = sorted(self.allowed_tools)
        tool_list = ", ".join(tools)
        return (
            "You may use tools. To call a tool, reply EXACTLY in this format:\n"
            "TOOL: tool_name\n"
            "{ \"arg\": \"value\" }\n\n"
            "To send a message to internal chat, reply EXACTLY:\n"
            "SAY channel=room:all priority=normal\n"
            "your natural-language message\n\n"
            f"Allowed tools for you: {tool_list}\n"
        )

    def _firm_context(self) -> str:
        wl = ", ".join(self.watchlist[:20]) if self.watchlist else "(none)"
        rl = json.dumps(self.risk_limits, indent=2) if self.risk_limits else "{}"
        return f"Watchlist: {wl}\nRisk limits (hard): {rl}"

    def _llm_priority_for_inbox(self, inbox: list[Message]) -> int:
        # Urgent messages should bypass background work
        if any(m.priority >= 10 for m in inbox):
            return min(self.llm_priority, 0)
        return self.llm_priority

    async def step(self, inbox: list[Message]) -> None:
        digest = self._build_inbox_digest(inbox)
        await self.state.update(self.cfg.id, status="thinking", current_activity="building plan")

        ctx = ToolContext(agent_id=self.cfg.id, agent_name=self.cfg.name)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt.strip()},
            {"role": "system", "content": self._tool_instructions()},
            {"role": "system", "content": self._firm_context()},
        ]

        if self._history:
            messages.extend(self._history[-12:])

        messages.append({"role": "user", "content": f"INBOX:\n{digest}\n\nWhat will you do next?"})

        llm_priority = self._llm_priority_for_inbox(inbox)

        for iter_idx in range(self.max_tool_iters):
            await self.state.update(self.cfg.id, current_activity=f"LLM call (iter {iter_idx+1})")
            out = await self.llm.chat(model=self.cfg.model, messages=messages, priority=llm_priority)
            parsed = parse_agent_output(out)

            messages.append({"role": "assistant", "content": out})
            self._history.append({"role": "assistant", "content": out})

            if parsed.kind == "tool" and parsed.tool_name:
                tool = parsed.tool_name
                if tool not in self.allowed_tools:
                    err = {"ok": False, "error": f"tool_not_allowed:{tool}"}
                    messages.append({"role": "user", "content": f"TOOL_RESULT name={tool}\n{orjson.dumps(err).decode('utf-8')}"})
                    continue

                args = parsed.tool_args or {}
                await self.state.update(self.cfg.id, last_tool=tool, current_activity=f"tool:{tool}")
                res = await self.tools.dispatch(ctx, tool, args)
                messages.append({"role": "user", "content": f"TOOL_RESULT name={tool}\n{orjson.dumps(res).decode('utf-8')}"})
                self._history.append({"role": "user", "content": f"TOOL_RESULT {tool}: {_truncate(orjson.dumps(res).decode('utf-8'), 800)}"})
                continue

            if parsed.kind == "say":
                ch = parsed.channel or self.default_channel
                content = parsed.content or ""
                pr = parsed.priority
                await self.state.update(self.cfg.id, status="communicating", current_activity=f"posting to {ch}")
                self.bus.publish(Message.create(channel=ch, sender=self.cfg.id, content=content, priority=pr))
                await self.state.update(self.cfg.id, status="running", current_activity="idle")
                return

        await self.state.update(self.cfg.id, status="running", current_activity="max tool iterations reached")
        self.bus.publish(
            Message.create(
                channel=self.default_channel,
                sender=self.cfg.id,
                content="(FYI) I reached my tool-iteration limit; waiting for more instructions.",
            )
        )
