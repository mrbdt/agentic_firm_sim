from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import orjson
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from firm_sim.config import settings, alpaca_settings
from firm_sim.db.sqlite import init_db, fetch_recent_messages, fetch_recent_orders
from firm_sim.db.writer import DBWriter
from firm_sim.bus import MessageBus, Message
from firm_sim.state import StateStore
from firm_sim.tools import OllamaClient, WebTools, MarketData, Broker, ToolBox
from firm_sim.tools.alpaca_rest import AlpacaREST, AlpacaConfig
from firm_sim.agents.registry import load_agents
from firm_sim.order_store import OrderRow


class ChairmanToCEO(BaseModel):
    message: str
    priority: str | None = "normal"  # normal|high


class PostChat(BaseModel):
    sender: str = "chairman"
    content: str
    priority: str | None = "normal"


def make_app() -> FastAPI:
    app = FastAPI(title="Agentic Firm Simulator", version="0.1.0")

    # Serve static UI
    static_dir = Path(__file__).parent / "ui" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (static_dir / "index.html").read_text(encoding="utf-8")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "ts": time.time()}

    @app.on_event("startup")
    async def _startup() -> None:
        await init_db(settings.sqlite_path)

        dbw = DBWriter(settings.sqlite_path, flush_interval_s=settings.persist_flush_interval_s)
        await dbw.start()

        bus = MessageBus(ring_size=settings.bus_ring_size, dbwriter=dbw)
        state = StateStore(dbwriter=dbw)

        # Alpaca clients
        alpaca_rest = None
        if alpaca_settings.key_id and alpaca_settings.secret_key:
            alpaca_rest = AlpacaREST(
                AlpacaConfig(
                    key_id=alpaca_settings.key_id,
                    secret_key=alpaca_settings.secret_key,
                    base_url=alpaca_settings.base_url,
                    data_url=alpaca_settings.data_url,
                )
            )

        market = MarketData(alpaca=alpaca_rest)
        broker = Broker(alpaca=alpaca_rest)
        web = WebTools()
        llm = OllamaClient(settings.ollama_base_url, max_concurrency=settings.llm_max_concurrency)

        tools = ToolBox(bus=bus, web=web, market=market, broker=broker)

        risk_limits = {
            "max_position_usd": settings.max_position_usd,
            "max_gross_exposure_usd": settings.max_gross_exposure_usd,
        }

        agents, firm_cfg = load_agents(
            settings.agents_config,
            bus=bus,
            state=state,
            llm=llm,
            tools=tools,
            risk_limits=risk_limits,
        )

        # Order recorder task: listens for trade_executed messages and persists to orders table.
        recorder_task = asyncio.create_task(_order_recorder_loop(bus, dbw), name="order_recorder")

        # Start agents
        for a in agents:
            await a.start()

        bus.publish(Message.create(channel="room:all", sender="system", content="Firm booted. Agents are online."))

        app.state.dbw = dbw
        app.state.bus = bus
        app.state.state_store = state
        app.state.llm = llm
        app.state.web = web
        app.state.market = market
        app.state.broker = broker
        app.state.tools = tools
        app.state.agents = agents
        app.state.recorder_task = recorder_task

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # stop agents
        for a in getattr(app.state, "agents", []):
            try:
                await a.stop()
            except Exception:
                pass

        # stop recorder
        rt = getattr(app.state, "recorder_task", None)
        if rt:
            rt.cancel()
            try:
                await rt
            except Exception:
                pass

        # close clients
        llm: OllamaClient | None = getattr(app.state, "llm", None)
        web: WebTools | None = getattr(app.state, "web", None)
        if llm:
            await llm.aclose()
        if web:
            await web.aclose()
        try:
            alpaca_rest = getattr(getattr(app.state, "broker", None), "alpaca", None)
            if alpaca_rest:
                await alpaca_rest.aclose()
        except Exception:
            pass

        # stop db writer
        dbw: DBWriter | None = getattr(app.state, "dbw", None)
        if dbw:
            await dbw.stop()

    # --- API ---

    @app.get("/api/agents")
    async def list_agents() -> dict[str, Any]:
        state: StateStore = app.state.state_store
        return {"agents": await state.snapshot()}

    @app.get("/api/agents/{agent_id}")
    async def get_agent(agent_id: str) -> dict[str, Any]:
        state: StateStore = app.state.state_store
        st = await state.get(agent_id)
        if not st:
            raise HTTPException(status_code=404, detail="agent not found")
        return st

    @app.get("/api/chat/{channel}")
    async def get_chat(channel: str, limit: int = 200) -> dict[str, Any]:
        bus: MessageBus = app.state.bus
        msgs = [m.to_dict() for m in bus.recent(channel, limit=limit)]
        if not msgs:
            rows = await fetch_recent_messages(settings.sqlite_path, channel, limit=limit)
            return {"channel": channel, "messages": rows}
        return {"channel": channel, "messages": msgs}

    @app.post("/api/chat/{channel}")
    async def post_chat(channel: str, payload: PostChat) -> dict[str, Any]:
        bus: MessageBus = app.state.bus
        pr = 10 if (payload.priority or "normal").lower() in ("high", "urgent", "p1") else 0
        msg = Message.create(channel=channel, sender=payload.sender, content=payload.content, priority=pr)
        bus.publish(msg)
        return {"ok": True, "message_id": msg.id}

    @app.post("/api/chairman/ceo")
    async def chairman_to_ceo(payload: ChairmanToCEO) -> dict[str, Any]:
        bus: MessageBus = app.state.bus
        pr = 10 if (payload.priority or "normal").lower() in ("high", "urgent", "p1") else 0
        msg = Message.create(channel="dm:chairman:ceo", sender="chairman", content=payload.message, priority=pr)
        bus.publish(msg)
        bus.publish(Message.create(channel="room:chairman", sender="chairman", content=payload.message, priority=pr))
        return {"ok": True, "message_id": msg.id}

    @app.get("/api/orders")
    async def orders(limit: int = 200) -> dict[str, Any]:
        rows = await fetch_recent_orders(settings.sqlite_path, limit=limit)
        return {"orders": rows}

    # WebSocket streaming of messages + state updates.
    @app.websocket("/ws")
    async def ws(ws: WebSocket) -> None:
        await ws.accept()

        bus: MessageBus = app.state.bus
        state: StateStore = app.state.state_store

        msg_q = bus.subscribe_global(max_queue=2000)
        st_q = state.subscribe(max_queue=2000)

        await ws.send_text(orjson.dumps({"type": "snapshot", "agents": await state.snapshot()}).decode("utf-8"))

        async def _forward_messages() -> None:
            while True:
                m = await msg_q.get()
                await ws.send_text(orjson.dumps({"type": "message", "data": m.to_dict()}).decode("utf-8"))

        async def _forward_states() -> None:
            while True:
                s = await st_q.get()
                await ws.send_text(orjson.dumps({"type": "state", "data": s.to_dict()}).decode("utf-8"))

        async def _receive() -> None:
            while True:
                await ws.receive_text()

        tasks = [
            asyncio.create_task(_forward_messages()),
            asyncio.create_task(_forward_states()),
            asyncio.create_task(_receive()),
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for t in pending:
                t.cancel()
        except WebSocketDisconnect:
            pass
        finally:
            bus.unsubscribe_global(msg_q)
            state.unsubscribe(st_q)
            for t in tasks:
                t.cancel()

    return app


async def _order_recorder_loop(bus: MessageBus, dbw: DBWriter) -> None:
    q = bus.subscribe_global(max_queue=5000)
    try:
        while True:
            m = await q.get()
            meta = m.meta or {}
            if meta.get("kind") != "trade_executed":
                continue
            ticket = meta.get("ticket") or {}
            order = meta.get("order") or {}
            row = OrderRow(
                id=str(ticket.get("id") or m.id),
                ts=float(m.ts),
                symbol=str(ticket.get("symbol") or ""),
                side=str(ticket.get("side") or ""),
                qty=float(ticket.get("qty") or 0.0),
                order_type=str(ticket.get("order_type") or "market"),
                status=str(order.get("status") or ""),
                broker_order_id=(str(order.get("broker_order_id")) if order.get("broker_order_id") else None),
                meta_json=orjson.dumps(meta).decode("utf-8"),
            )
            dbw.enqueue_order(row)
    finally:
        bus.unsubscribe_global(q)


app = make_app()
