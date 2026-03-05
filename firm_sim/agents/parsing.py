from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ParsedOutput:
    kind: str  # "tool" or "say"
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    channel: str | None = None
    priority: int = 0
    content: str | None = None


_TOOL_RE = re.compile(r"^TOOL\s*(?::|name=)?\s*([a-zA-Z0-9_\-]+)\s*$", re.IGNORECASE)
_SAY_HDR_RE = re.compile(r"^SAY\s+channel=([^\s]+)(?:\s+priority=([^\s]+))?\s*$", re.IGNORECASE)


def parse_agent_output(text: str) -> ParsedOutput:
    """Parse a single-step agent output.

    Supported formats:

    Tool call:
        TOOL: web_search
        {"query": "...", "max_results": 5}

    Message:
        SAY channel=room:all priority=normal
        Hello team...
    """
    raw = (text or "").strip()
    if not raw:
        return ParsedOutput(kind="say", channel="room:all", priority=0, content="")

    lines = raw.splitlines()
    # tool
    if lines:
        m = _TOOL_RE.match(lines[0].strip())
        if m:
            tool_name = m.group(1)
            # remaining lines is JSON args (best-effort)
            args_txt = "\n".join(lines[1:]).strip()
            args: dict[str, Any] = {}
            if args_txt:
                try:
                    args = json.loads(args_txt)
                except Exception:
                    # allow "INPUT: {..}"
                    args_txt2 = re.sub(r"^INPUT\s*:\s*", "", args_txt, flags=re.IGNORECASE).strip()
                    try:
                        args = json.loads(args_txt2)
                    except Exception:
                        args = {"_raw": args_txt}
            return ParsedOutput(kind="tool", tool_name=tool_name, tool_args=args)

    # say
    if lines:
        m2 = _SAY_HDR_RE.match(lines[0].strip())
        if m2:
            channel = m2.group(1).strip()
            pr = (m2.group(2) or "normal").lower()
            priority = 10 if pr in ("high", "urgent", "p1") else 0
            content = "\n".join(lines[1:]).strip()
            return ParsedOutput(kind="say", channel=channel, priority=priority, content=content)

    # default: say to room:all
    return ParsedOutput(kind="say", channel="room:all", priority=0, content=raw)
