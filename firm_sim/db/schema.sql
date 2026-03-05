-- SQLite schema for the firm simulator

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  channel TEXT NOT NULL,
  sender TEXT NOT NULL,
  content TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  meta TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_channel_ts ON messages(channel, ts);

CREATE TABLE IF NOT EXISTS agent_state (
  agent_id TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  qty REAL NOT NULL,
  order_type TEXT NOT NULL,
  status TEXT NOT NULL,
  broker_order_id TEXT,
  meta TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_ts ON orders(ts);
