from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque

from firm_sim.bus.models import Message


@dataclass
class Subscription:
    queue: "asyncio.Queue[Message]"
    channels: list[str]
    bus: "MessageBus"
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.bus._unsubscribe(self.queue, self.channels)


class MessageBus:
    """In-memory pub/sub with:
    - per-channel ring buffers
    - per-channel subscribers
    - global subscribers (for UI/websocket fanout)
    - a bounded ID index to allow O(1) lookup of recent messages

    Persistence is handled by an external DBWriter (if attached).
    """

    def __init__(self, ring_size: int = 500, *, id_index_size: int = 10_000, dbwriter=None) -> None:
        self.ring_size = int(ring_size)
        self._buffers: dict[str, Deque[Message]] = defaultdict(lambda: deque(maxlen=self.ring_size))
        self._subs: dict[str, set[asyncio.Queue[Message]]] = defaultdict(set)
        self._global_subs: set[asyncio.Queue[Message]] = set()

        self._id_index_size = int(id_index_size)
        self._id_index: dict[str, Message] = {}
        self._id_index_order: Deque[str] = deque()  # manual eviction

        self._dbwriter = dbwriter  # optional, must implement enqueue_message(msg)

    def attach_dbwriter(self, dbwriter) -> None:
        self._dbwriter = dbwriter

    def publish(self, msg: Message) -> None:
        # Store in ring buffer
        self._buffers[msg.channel].append(msg)

        # Update ID index with manual eviction
        self._id_index[msg.id] = msg
        self._id_index_order.append(msg.id)
        while len(self._id_index_order) > self._id_index_size:
            old = self._id_index_order.popleft()
            self._id_index.pop(old, None)

        # Fan out to subscribers
        for q in list(self._subs.get(msg.channel, [])):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

        # Fan out to global subscribers
        for q in list(self._global_subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

        # Persist (best-effort)
        if self._dbwriter is not None:
            try:
                self._dbwriter.enqueue_message(msg)
            except Exception:
                pass

    def recent(self, channel: str, limit: int = 200) -> list[Message]:
        buf = self._buffers.get(channel)
        if not buf:
            return []
        if limit >= len(buf):
            return list(buf)
        return list(buf)[-limit:]

    def get_by_id(self, message_id: str) -> Message | None:
        return self._id_index.get(message_id)

    def subscribe(self, channels: list[str], *, max_queue: int = 500) -> Subscription:
        q: asyncio.Queue[Message] = asyncio.Queue(maxsize=max_queue)
        for ch in channels:
            self._subs[ch].add(q)
        return Subscription(queue=q, channels=channels, bus=self)

    def subscribe_global(self, *, max_queue: int = 1000) -> asyncio.Queue[Message]:
        q: asyncio.Queue[Message] = asyncio.Queue(maxsize=max_queue)
        self._global_subs.add(q)
        return q

    def unsubscribe_global(self, q: asyncio.Queue[Message]) -> None:
        self._global_subs.discard(q)

    def _unsubscribe(self, q: asyncio.Queue[Message], channels: list[str]) -> None:
        for ch in channels:
            self._subs[ch].discard(q)
