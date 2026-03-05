from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    """Tiny TTL cache (not thread-safe)."""

    def __init__(self, ttl_s: float, max_items: int = 256) -> None:
        self.ttl_s = float(ttl_s)
        self.max_items = int(max_items)
        self._data: dict[str, _Entry] = {}

    def get(self, key: str) -> Any | None:
        e = self._data.get(key)
        if not e:
            return None
        if e.expires_at < time.time():
            self._data.pop(key, None)
            return None
        return e.value

    def set(self, key: str, value: Any) -> None:
        if len(self._data) >= self.max_items:
            # simple eviction: drop oldest expiry
            oldest = min(self._data.items(), key=lambda kv: kv[1].expires_at)[0]
            self._data.pop(oldest, None)
        self._data[key] = _Entry(value=value, expires_at=time.time() + self.ttl_s)

    def get_or_set(self, key: str, fn: Callable[[], Any]) -> Any:
        v = self.get(key)
        if v is not None:
            return v
        v = fn()
        self.set(key, v)
        return v
