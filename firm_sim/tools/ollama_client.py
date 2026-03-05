from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class OllamaError(RuntimeError):
    pass


@dataclass(slots=True)
class _ChatReq:
    model: str
    messages: list[dict[str, str]]
    options: dict[str, Any] | None
    temperature: float | None
    fut: asyncio.Future[str]


class OllamaClient:
    """Async Ollama client with a priority-aware request scheduler.

    Why: in a multi-agent system, you don't want low-value background calls to block
    high-priority Chairman/CEO interactions. This client runs a small worker pool
    and processes requests from an asyncio.PriorityQueue.
    """

    def __init__(self, base_url: str, *, max_concurrency: int = 2, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_s)
        self._client = httpx.AsyncClient(timeout=self._timeout)

        self._q: asyncio.PriorityQueue[tuple[int, float, _ChatReq]] = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._closed = False

        n = max(1, int(max_concurrency))
        for i in range(n):
            self._workers.append(asyncio.create_task(self._worker(i), name=f"ollama_worker_{i}"))

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        for t in self._workers:
            t.cancel()
        for t in self._workers:
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._workers.clear()
        await self._client.aclose()

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        temperature: float | None = None,
        priority: int = 5,
    ) -> str:
        if self._closed:
            raise OllamaError("OllamaClient is closed")

        fut: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        req = _ChatReq(model=model, messages=messages, options=options, temperature=temperature, fut=fut)
        await self._q.put((int(priority), time.time(), req))
        return await fut

    async def _worker(self, worker_id: int) -> None:
        while True:
            pr, ts, req = await self._q.get()
            if req.fut.cancelled():
                continue
            try:
                out = await self._do_chat(req.model, req.messages, options=req.options, temperature=req.temperature)
                if not req.fut.cancelled():
                    req.fut.set_result(out)
            except Exception as e:
                if not req.fut.cancelled():
                    req.fut.set_exception(e)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.6, min=0.6, max=4),
        retry=retry_if_exception_type((httpx.HTTPError, OllamaError)),
        reraise=True,
    )
    async def _do_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        options: dict[str, Any] | None = None,
        temperature: float | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options
        if temperature is not None:
            payload.setdefault("options", {})
            payload["options"]["temperature"] = temperature

        r = await self._client.post(f"{self.base_url}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()

        msg = data.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str):
            raise OllamaError(f"Bad response from Ollama: {data}")
        return content
