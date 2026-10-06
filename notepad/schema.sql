-- The notepad. Four tables. Applied by notepad.py on first use.
-- Allowed values (person, kind, status, closed_how) are checked in notepad.py, not here,
-- so the table definitions stay plain.

CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY,
  person TEXT NOT NULL,
  department TEXT,
  kind TEXT NOT NULL DEFAULT 'needs_you',
  waiting TEXT NOT NULL,
  line TEXT NOT NULL,
  action_label TEXT,
  action_instruction TEXT,
  link_url TEXT,
  added_by TEXT NOT NULL,
  quote TEXT,
  waiting_since TEXT,
  rank INTEGER NOT NULL DEFAULT 100,
  status TEXT NOT NULL DEFAULT 'open',
  closed_how TEXT,
  closed_why TEXT,
  closed_at TEXT,
  standing TEXT,
  source_ref TEXT,
  slack_channel TEXT,
  slack_thread_ts TEXT,
  session_id TEXT,
  session_is_shared INTEGER NOT NULL DEFAULT 0,
  seen_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences(
  person TEXT, key TEXT, value TEXT, quote TEXT, set_at TEXT,
  PRIMARY KEY(person, key)
);

CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  item_id INTEGER,
  run_id INTEGER,
  action TEXT NOT NULL,
  detail TEXT
);

CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY,
  department TEXT NOT NULL,
  person TEXT NOT NULL,
  model TEXT,
  effort TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  seconds INTEGER,
  status TEXT NOT NULL DEFAULT 'running',
  tokens_in INTEGER, tokens_out INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER,
  subagents INTEGER, cost_usd REAL, session_id TEXT,
  items_added INTEGER, items_closed INTEGER, emails_archived INTEGER, mode TEXT, note TEXT
);

-- Rule 6: one open item per (person, department, source_ref).
CREATE UNIQUE INDEX IF NOT EXISTS items_open_source
  ON items(person, IFNULL(department, ''), source_ref)
  WHERE source_ref IS NOT NULL AND status IN ('open', 'working');

CREATE INDEX IF NOT EXISTS items_by_person ON items(person, status, kind, rank, waiting_since);
CREATE INDEX IF NOT EXISTS items_by_closed ON items(person, closed_how, closed_at);
CREATE INDEX IF NOT EXISTS events_by_item ON events(item_id);
CREATE INDEX IF NOT EXISTS events_by_run ON events(run_id);
CREATE INDEX IF NOT EXISTS events_by_action ON events(action, at);
CREATE INDEX IF NOT EXISTS events_by_at ON events(at);
CREATE INDEX IF NOT EXISTS runs_by_dept ON runs(department, person, id);

-- Rule 5, enforced by the database too: events are append-only.
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
