from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

import aiosqlite
import orjson

from firm_sim.bus.models import Message
from firm_sim.state import AgentState
from firm_sim.order_store import OrderRow


WriteKind = Literal["message", "state", "order"]


@dataclass(slots=True)
class WriteEvent:
    kind: WriteKind
    payload: Any


class DBWriter:
    """Single SQLite writer task.

    Motivation:
    - SQLite only allows one writer at a time.
    - Opening a new connection per flush is slow.
    - A single writer queue prevents 'database is locked' storms.

    This writer is **best-effort**: when overloaded it may drop events.
    """

    def __init__(self, sqlite_path: str, *, flush_interval_s: float = 0.5, max_queue: int = 50_000) -> None:
        self.sqlite_path = sqlite_path
        self.flush_interval_s = float(flush_interval_s)
        self._q: asyncio.Queue[WriteEvent] = asyncio.Queue(maxsize=int(max_queue))
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="db_writer")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def enqueue_message(self, msg: Message) -> None:
        try:
            self._q.put_nowait(WriteEvent(kind="message", payload=msg))
        except asyncio.QueueFull:
            pass

    def enqueue_state(self, st: AgentState) -> None:
        try:
            self._q.put_nowait(WriteEvent(kind="state", payload=st))
        except asyncio.QueueFull:
            pass

    def enqueue_order(self, row: OrderRow) -> None:
        try:
            self._q.put_nowait(WriteEvent(kind="order", payload=row))
        except asyncio.QueueFull:
            pass

    async def _loop(self) -> None:
        # Collapsing buffers
        message_rows: list[tuple[str, float, str, str, str, int, str | None]] = []
        state_latest: dict[str, tuple[str, float, str]] = {}
        order_rows: list[tuple[str, float, str, str, float, str, str, str | None, str | None]] = []

        async with aiosqlite.connect(self.sqlite_path) as db:
            # WAL is enabled by schema init; keep transactions short.
            last_flush = time.time()

            while not self._stop.is_set():
                timeout = max(0.0, self.flush_interval_s - (time.time() - last_flush))
                try:
                    ev = await asyncio.wait_for(self._q.get(), timeout=timeout)
                    if ev.kind == "message":
                        m: Message = ev.payload
                        message_rows.append(
                            (
                                m.id,
                                float(m.ts),
                                m.channel,
                                m.sender,
                                m.content,
                                int(m.priority),
                                orjson.dumps(m.meta).decode("utf-8") if m.meta else None,
                            )
                        )
                    elif ev.kind == "state":
                        st: AgentState = ev.payload
                        ts = float(st.updated_ts or time.time())
                        state_latest[st.agent_id] = (st.agent_id, ts, orjson.dumps(st.to_dict()).decode("utf-8"))
                    elif ev.kind == "order":
                        r: OrderRow = ev.payload
                        order_rows.append(
                            (
                                r.id,
                                float(r.ts),
                                r.symbol,
                                r.side,
                                float(r.qty),
                                r.order_type,
                                r.status,
                                r.broker_order_id,
                                r.meta_json,
                            )
                        )

                    # Flush if large
                    if len(message_rows) >= 500 or len(order_rows) >= 200 or len(state_latest) >= 200:
                        await self._flush(db, message_rows, state_latest, order_rows)
                        message_rows.clear()
                        state_latest.clear()
                        order_rows.clear()
                        last_flush = time.time()

                except asyncio.TimeoutError:
                    if message_rows or state_latest or order_rows:
                        await self._flush(db, message_rows, state_latest, order_rows)
                        message_rows.clear()
                        state_latest.clear()
                        order_rows.clear()
                    last_flush = time.time()
                except Exception:
                    # Keep writer alive.
                    await asyncio.sleep(0.25)

            # Final flush
            if message_rows or state_latest or order_rows:
                await self._flush(db, message_rows, state_latest, order_rows)

    async def _flush(
        self,
        db: aiosqlite.Connection,
        message_rows: list[tuple[str, float, str, str, str, int, str | None]],
        state_latest: dict[str, tuple[str, float, str]],
        order_rows: list[tuple[str, float, str, str, float, str, str, str | None, str | None]],
    ) -> None:
        try:
            if message_rows:
                await db.executemany(
                    "INSERT OR REPLACE INTO messages(id, ts, channel, sender, content, priority, meta) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    message_rows,
                )
            if state_latest:
                await db.executemany(
                    "INSERT OR REPLACE INTO agent_state(agent_id, ts, state) VALUES (?, ?, ?)",
                    list(state_latest.values()),
                )
            if order_rows:
                await db.executemany(
                    "INSERT OR REPLACE INTO orders(id, ts, symbol, side, qty, order_type, status, broker_order_id, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    order_rows,
                )
            await db.commit()
        except Exception:
            # Ignore commit errors (best-effort)
            try:
                await db.rollback()
            except Exception:
                pass
