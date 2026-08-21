-- Couple budget tracker — D1 schema.
-- Apply with: wrangler d1 execute couple-budget-db --remote --file=schema.sql
-- Safe to re-run: everything is IF NOT EXISTS / OR IGNORE.

CREATE TABLE IF NOT EXISTS settings (
  id               INTEGER PRIMARY KEY CHECK (id = 1),
  monthly_income   REAL    NOT NULL DEFAULT 0,
  savings_goal     REAL    NOT NULL DEFAULT 0,
  month_start_day  INTEGER NOT NULL DEFAULT 1,
  categories       TEXT    NOT NULL DEFAULT '["סופר","אוכל בחוץ","דלק ורכב","ילדים","בילויים","ביגוד","בית","בריאות","מתנות","אחר"]',
  users            TEXT    NOT NULL DEFAULT '[]',
  setup_done       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fixed_expenses (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  name     TEXT NOT NULL,
  amount   REAL NOT NULL,
  category TEXT NOT NULL DEFAULT 'בית',
  active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS transactions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           TEXT NOT NULL,              -- ISO datetime, Israel time
  amount       REAL NOT NULL,
  description  TEXT NOT NULL DEFAULT '',
  category     TEXT NOT NULL DEFAULT 'אחר',
  created_by   TEXT NOT NULL DEFAULT '',
  source       TEXT NOT NULL DEFAULT 'web', -- 'web' | 'whatsapp'
  budget_month TEXT NOT NULL                -- e.g. '2026-08'
);
CREATE INDEX IF NOT EXISTS idx_tx_month ON transactions(budget_month);

CREATE TABLE IF NOT EXISTS months_archive (
  month       TEXT PRIMARY KEY,  -- e.g. '2026-08'
  budget      REAL NOT NULL,
  total_spent REAL NOT NULL,
  balance     REAL NOT NULL,
  closed_at   TEXT NOT NULL
);

INSERT OR IGNORE INTO settings (id) VALUES (1);
