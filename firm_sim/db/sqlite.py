from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from firm_sim.db import schema


async def init_db(sqlite_path: str) -> None:
    path = Path(sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(sqlite_path) as db:
        await db.executescript(schema.SCHEMA_SQL)
        await db.commit()


async def insert_messages(sqlite_path: str, rows: Iterable[tuple[str, float, str, str, str, int, str | None]]) -> None:
    async with aiosqlite.connect(sqlite_path) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO messages(id, ts, channel, sender, content, priority, meta) VALUES (?, ?, ?, ?, ?, ?, ?)",
            list(rows),
        )
        await db.commit()


async def upsert_agent_states(sqlite_path: str, rows: Iterable[tuple[str, float, str]]) -> None:
    async with aiosqlite.connect(sqlite_path) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO agent_state(agent_id, ts, state) VALUES (?, ?, ?)",
            list(rows),
        )
        await db.commit()


async def insert_orders(sqlite_path: str, rows: Iterable[tuple[str, float, str, str, float, str, str, str | None, str | None]]) -> None:
    async with aiosqlite.connect(sqlite_path) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO orders(id, ts, symbol, side, qty, order_type, status, broker_order_id, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            list(rows),
        )
        await db.commit()


async def fetch_recent_messages(sqlite_path: str, channel: str, limit: int = 100) -> list[dict[str, Any]]:
    async with aiosqlite.connect(sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, ts, channel, sender, content, priority, meta FROM messages WHERE channel = ? ORDER BY ts DESC LIMIT ?",
            (channel, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]


async def fetch_agent_states(sqlite_path: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT agent_id, ts, state FROM agent_state")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def fetch_recent_orders(sqlite_path: str, limit: int = 200) -> list[dict[str, Any]]:
    async with aiosqlite.connect(sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, ts, symbol, side, qty, order_type, status, broker_order_id, meta FROM orders ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]
