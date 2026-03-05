from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass(slots=True)
class Message:
    id: str
    ts: float
    channel: str
    sender: str
    content: str
    priority: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def create(channel: str, sender: str, content: str, *, priority: int = 0, meta: dict[str, Any] | None = None) -> "Message":
        return Message(
            id=new_id("msg"),
            ts=time.time(),
            channel=channel,
            sender=sender,
            content=content,
            priority=priority,
            meta=meta or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "channel": self.channel,
            "sender": self.sender,
            "content": self.content,
            "priority": self.priority,
            "meta": self.meta,
        }
