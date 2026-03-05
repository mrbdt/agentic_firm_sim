from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

try:
    from duckduckgo_search import DDGS  # type: ignore
except Exception:  # pragma: no cover
    DDGS = None  # type: ignore

try:
    import trafilatura  # type: ignore
except Exception:  # pragma: no cover
    trafilatura = None  # type: ignore

from firm_sim.tools.cache import TTLCache


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class WebTools:
    def __init__(self) -> None:
        self._search_cache = TTLCache(ttl_s=300, max_items=256)
        self._open_cache = TTLCache(ttl_s=600, max_items=256)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AgenticFirmSim/0.1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
        q = query.strip()
        if not q:
            return []
        key = f"ddg:{max_results}:{q.lower()}"
        cached = self._search_cache.get(key)
        if cached is not None:
            return cached

        if DDGS is None:
            # minimal fallback: no search provider installed
            return []

        def _run() -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            with DDGS() as ddgs:
                for r in ddgs.text(q, max_results=max_results):
                    out.append(
                        SearchResult(
                            title=str(r.get("title", "")),
                            url=str(r.get("href") or r.get("url") or ""),
                            snippet=str(r.get("body") or r.get("snippet") or ""),
                        ).to_dict()
                    )
            # de-dup URLs
            seen = set()
            dedup = []
            for r in out:
                u = r.get("url")
                if not u or u in seen:
                    continue
                seen.add(u)
                dedup.append(r)
            return dedup

        results = await asyncio.to_thread(_run)
        self._search_cache.set(key, results)
        return results

    async def open_url(self, url: str, *, max_chars: int = 8000) -> dict[str, Any]:
        u = url.strip()
        if not u:
            return {"url": url, "text": ""}

        key = f"open:{max_chars}:{u}"
        cached = self._open_cache.get(key)
        if cached is not None:
            return cached

        try:
            r = await self._client.get(u)
            r.raise_for_status()
            html = r.text
        except Exception:
            return {"url": u, "text": ""}

        text = self._extract_text(html, url=u)
        if len(text) > max_chars:
            text = text[:max_chars] + "…"

        out = {"url": u, "text": text}
        self._open_cache.set(key, out)
        return out

    def _extract_text(self, html: str, *, url: str = "") -> str:
        if trafilatura is not None:
            try:
                extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
                if extracted:
                    return self._clean(extracted)
            except Exception:
                pass

        soup = BeautifulSoup(html, "lxml")
        # remove scripts/styles/nav
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text_parts = []
        for el in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            t = el.get_text(" ", strip=True)
            if t:
                text_parts.append(t)
        text = "\n".join(text_parts)
        return self._clean(text)

    def _clean(self, text: str) -> str:
        text = re.sub(r"\s+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()
