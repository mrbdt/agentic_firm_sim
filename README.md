# Agentic Firm Simulator (from first principles)

This repository is a **multi-agent trading-firm simulator** built around:
- a FastAPI backend,
- an internal natural-language chat bus between "employees",
- **web-search capable LLM agents** (designed for **Qwen 3.5** models served by **Ollama**),
- market data via **Alpaca** (preferred) and **Yahoo Finance** (fallback),
- a simple risk + execution pipeline that can place **paper trades** through Alpaca.

> ⚠️ **Important**: This is a simulation framework / engineering reference.
> If you connect it to real brokerage credentials you do so at your own risk.
> Start with **Alpaca paper trading** and strict risk limits.

---

## What you get

### Firm structure (default)
- **CEO**: routes work, answers the Chairman, selects trades to push through risk.
- **Researcher**: web-searches catalysts / macro / headlines and posts internal memos.
- **PM**: turns research + prices into trade proposals.
- **Risk Officer**: deterministic guardrails + LLM explanation; approves/rejects intents.
- **Execution**: converts approved intents into Alpaca paper orders and reports fills.

Agents communicate **in natural language** in internal chat rooms and DMs.

### Observability
- Each agent continuously updates a live state object:
  - `status`, `current_objective`, `current_activity`
  - `last_tool`, `last_error`
  - `inbox_depth`, `last_update`
- The UI shows **what everyone is doing right now**.
- WebSocket streaming: chat + state updates in near real-time.

### Performance / bottleneck avoidance
- Fully **async** FastAPI + httpx.
- Global **LLM concurrency semaphore** to avoid self-inflicted overload.
- Message persistence is **batched** in the background.
- Web search + Yahoo finance calls are cached with TTL.

---

## Quick start

### 0) Prerequisites
- Python 3.10+ (3.11/3.12 recommended)
- Ollama installed + running, with Qwen models pulled, e.g.
  - `ollama pull qwen2.5:7b-instruct` (example)
  - you will set the exact model names in `configs/agents.yaml`

> This project assumes Ollama's HTTP API at `http://localhost:11434`.

### 1) Install
```bash
cd agentic_firm_sim
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure environment
Copy `.env.example` to `.env` and fill in:
- `ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`
- `ALPACA_PAPER=1` (recommended)

```bash
cp .env.example .env
```

### 3) Configure agents
Edit `configs/agents.yaml` and set each agent's `model` to the Ollama model you have locally.

### 4) Run
```bash
bash scripts/run_backend.sh
```

Open:
- http://127.0.0.1:8000  (simple dashboard)

---

## Chairman controls

### Chat with the CEO
In the UI, use the **CEO Chat** panel.

Or via API:
```bash
curl -X POST http://127.0.0.1:8000/api/chairman/ceo   -H "Content-Type: application/json"   -d '{"message":"Give me a 60s briefing. What are the top risks today?"}'
```

### Send a top-priority directive
```bash
curl -X POST http://127.0.0.1:8000/api/chairman/ceo   -H "Content-Type: application/json"   -d '{"message":"Stop all new trades and reduce gross exposure below $10k.", "priority":"high"}'
```

---

## Design notes

- Agents speak to each other in **natural language** in chat.
- The execution boundary is guarded: only the Execution agent can place orders.
- Trade proposals still carry a **structured ticket** in message metadata so that risk/execution can be deterministic.

---

## Repo layout

- `firm_sim/main.py` — FastAPI app + startup orchestration
- `firm_sim/agents/` — LLM-driven employees
- `firm_sim/tools/` — Ollama client, web tools, Alpaca + Yahoo market data
- `firm_sim/bus/` — internal message bus + WebSocket fanout
- `firm_sim/ui/static/` — minimal dashboard

---

## License
MIT (see `LICENSE`).
