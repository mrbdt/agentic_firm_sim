from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class AgentState:
    agent_id: str
    name: str
    title: str
    role: str

    status: str = "starting"
    current_objective: str = ""
    current_activity: str = ""
    last_tool: str = ""
    last_error: str = ""
    inbox_depth: int = 0
    updated_ts: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StateStore:
    """In-memory agent state + subscriptions for streaming.

    Persistence is handled by an external DBWriter (if attached).
    """

    def __init__(self, *, dbwriter=None) -> None:
        self._states: dict[str, AgentState] = {}
        self._lock = asyncio.Lock()

        self._subs: set[asyncio.Queue[AgentState]] = set()
        self._dbwriter = dbwriter  # optional, must implement enqueue_state(st)

    def attach_dbwriter(self, dbwriter) -> None:
        self._dbwriter = dbwriter

    async def register(self, state: AgentState) -> None:
        async with self._lock:
            state.updated_ts = time.time()
            self._states[state.agent_id] = state
        self._broadcast(state)
        self._persist(state)

    async def update(self, agent_id: str, **kwargs: Any) -> None:
        async with self._lock:
            st = self._states.get(agent_id)
            if not st:
                return
            for k, v in kwargs.items():
                if hasattr(st, k):
                    setattr(st, k, v)
            st.updated_ts = time.time()
        self._broadcast(st)
        self._persist(st)

    async def snapshot(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [s.to_dict() for s in self._states.values()]

    async def get(self, agent_id: str) -> dict[str, Any] | None:
        async with self._lock:
            st = self._states.get(agent_id)
            return st.to_dict() if st else None

    def subscribe(self, *, max_queue: int = 1000) -> asyncio.Queue[AgentState]:
        q: asyncio.Queue[AgentState] = asyncio.Queue(maxsize=max_queue)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[AgentState]) -> None:
        self._subs.discard(q)

    def _broadcast(self, st: AgentState) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(st)
            except asyncio.QueueFull:
                pass

    def _persist(self, st: AgentState) -> None:
        if self._dbwriter is None:
            return
        try:
            self._dbwriter.enqueue_state(st)
        except Exception:
            pass
