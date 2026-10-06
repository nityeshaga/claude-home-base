"""The notepad: one SQLite record of what each person needs to see. Every write goes
through here.

The seven rules (see README.md) live in this file, never in an agent's discipline.
Python 3 standard library only.
"""
import json
import os
import sqlite3
import time
from datetime import date, datetime, timedelta

import closed_topics

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "notepad.db")
SCHEMA = os.path.join(HERE, "schema.sql")
DEFAULT_CONFIG = os.path.join(HERE, "config.json")

KINDS = ("needs_you", "someday")
STATUS_BY_HOW = {"handled": "dealt_with", "dismissed": "dealt_with", "evidence": "dealt_with",
                 "superseded": "superseded", "stale": "stale"}
OPEN = ("open", "working")
UPDATABLE = ("line", "action_label", "action_instruction", "rank", "standing",
             "waiting_since", "link_url", "kind")
RUN_FIELDS = ("model", "effort", "seconds", "tokens_in", "tokens_out", "tokens_cache_read",
              "tokens_cache_write", "subagents", "cost_usd", "session_id", "items_added",
              "items_closed", "emails_archived", "mode", "note")


class Refused(Exception):
    """A rule said no. The message is the reason."""


# ---------- plumbing ----------

def db_path():
    return os.environ.get("NOTEPAD_DB") or DEFAULT_DB


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def config():
    """config.json next to this file (or NOTEPAD_CONFIG). Missing file -> {}."""
    try:
        with open(os.environ.get("NOTEPAD_CONFIG") or DEFAULT_CONFIG) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def people():
    """The people who have a notepad, from config. Empty = any name is accepted."""
    return tuple(config().get("people") or ())


def _is_person(name):
    known = people()
    if known:
        return name in known
    return bool(name) and not name.startswith(("agent", "session:")) and name != "unknown"


_ready = set()


def _connect():
    path = db_path()
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    if path not in _ready:
        # First use in this process: WAL + schema. Everything is IF NOT EXISTS, so racing
        # processes are harmless; the retry covers the moment one of them holds the lock.
        _retry(lambda: conn.execute("PRAGMA journal_mode=WAL"))
        with open(SCHEMA) as f:
            schema = f.read()
        _retry(lambda: conn.executescript(schema))
        _ready.add(path)
    return conn


def _retry(fn, tries=20):
    for i in range(tries):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            msg = str(e)
            if ("locked" not in msg and "busy" not in msg) or i == tries - 1:
                raise
            time.sleep(min(0.05 * (i + 1), 1.0))


def _write(fn):
    """Run fn(conn) in one short BEGIN IMMEDIATE transaction; retry if the db is busy."""
    def attempt():
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                out = fn(conn)
                conn.execute("COMMIT")
                return out
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
    return _retry(attempt)


def _read(sql, args=()):
    conn = _connect()
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def _event(conn, action, actor, item_id=None, run_id=None, detail=None):
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    cur = conn.execute("INSERT INTO events(at, actor, item_id, run_id, action, detail) "
                       "VALUES (?,?,?,?,?,?)", (now(), actor or "unknown", item_id, run_id, action, detail))
    return cur.lastrowid


def _item(conn, item_id):
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not row:
        raise LookupError(f"no item {item_id}")
    return dict(row)


def _guard_person(person):
    # Rule 4. A job that must never touch someone's notepad runs with their name here.
    locked = [p.strip() for p in os.environ.get("NOTEPAD_READONLY_FOR", "").split(",") if p.strip()]
    if person in locked:
        raise Refused(f"NOTEPAD_READONLY_FOR includes {person}: writes for {person} are off")


def _check_person(person):
    if not _is_person(person):
        known = people()
        raise ValueError(f"person must be one of {known}, got {person!r}" if known
                         else f"{person!r} is not a person's name")


# ---------- rule 3: closed topics ----------

def closed_ledger():
    return os.path.expanduser(os.environ.get("NOTEPAD_CLOSED_LEDGER")
                              or config().get("closed_ledger") or closed_topics.LEDGER)


def closed_topic(person, *texts):
    """-> the ledger quote if any text re-raises a closed topic for person, else None.
    Each field is matched as its own line."""
    entries = closed_topics.load(closed_ledger())
    lines = [" ".join(t.split()) for t in texts if t]
    found = closed_topics.hits(lines, entries, person)
    return found[0][1] if found else None


def _guard_closed(person, *texts):
    quote = closed_topic(person, *texts)
    if quote:
        raise Refused(f"closed topic for {person} in {closed_ledger()}: {quote}")


def _entry_test(added_by, waiting, line, label, instruction):
    # Rule 1.
    if added_by.startswith("agent"):
        missing = [n for n, v in (("waiting", waiting), ("line", line), ("action_label", label),
                                  ("action_instruction", instruction)) if not (v and str(v).strip())]
        if missing:
            raise Refused(f"entry test: an agent item needs {', '.join(missing)}")


# ---------- items ----------

def add_item(person, line, *, added_by, waiting=None, action_label=None, action_instruction=None,
             department=None, kind="needs_you", link_url=None, quote=None, waiting_since=None,
             rank=100, source_ref=None, session_id=None, session_is_shared=False, actor=None):
    _check_person(person)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    actor = actor or added_by
    _guard_person(person)
    if added_by.startswith("agent"):
        pass
    elif _is_person(added_by):
        # Rule 2. A person's own item needs only a line; a session or agent writing it for
        # them must carry their words.
        waiting = waiting or added_by
        if not (quote and quote.strip()) and (actor.startswith(("session:", "agent")) or actor == "unknown"):
            raise Refused(f"a session adding for {added_by} must pass their words with --quote")
    else:
        raise Refused(f"added_by must be a person's name or agent:<name>, got {added_by!r}")
    if not (line and line.strip()):
        raise Refused("an item needs a line")
    _entry_test(added_by, waiting, line, action_label, action_instruction)
    _guard_closed(person, line, action_label, action_instruction)

    def tx(conn):
        t = now()
        if source_ref:
            # Rule 6. The same source again updates the open item instead of adding one.
            row = conn.execute("SELECT * FROM items WHERE person=? AND IFNULL(department,'')=IFNULL(?,'') "
                               "AND source_ref=? AND status IN ('open','working')",
                               (person, department, source_ref)).fetchone()
            if row:
                given = {"line": line, "waiting": waiting, "action_label": action_label,
                         "action_instruction": action_instruction, "link_url": link_url,
                         "waiting_since": waiting_since, "session_id": session_id}
                changes = {k: v for k, v in given.items() if v is not None and v != row[k]}
                if rank != 100 and rank != row["rank"]:
                    changes["rank"] = rank
                if changes:
                    conn.execute(f"UPDATE items SET {', '.join(k + '=?' for k in changes)}, updated_at=? "
                                 "WHERE id=?", (*changes.values(), t, row["id"]))
                _event(conn, "item_readded", actor, item_id=row["id"],
                       detail={"source_ref": source_ref, "changes": changes})
                return dict(_item(conn, row["id"]), deduped=True)
        cur = conn.execute(
            "INSERT INTO items(person, department, kind, waiting, line, action_label, action_instruction, "
            "link_url, added_by, quote, waiting_since, rank, source_ref, session_id, session_is_shared, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (person, department, kind, waiting, line, action_label, action_instruction, link_url, added_by,
             quote, waiting_since or date.today().isoformat(), rank, source_ref, session_id,
             1 if session_is_shared else 0, t, t))
        item = _item(conn, cur.lastrowid)
        _event(conn, "item_added", actor, item_id=item["id"],
               detail={k: item[k] for k in ("person", "department", "kind", "waiting", "line",
                                            "action_label", "added_by", "quote", "source_ref")})
        return item
    return _write(tx)


def close_item(item_id, how, why=None, actor=None):
    if how not in STATUS_BY_HOW:
        raise ValueError(f"how must be one of {tuple(STATUS_BY_HOW)}")

    def tx(conn):
        item = _item(conn, item_id)
        _guard_person(item["person"])
        if item["status"] not in OPEN:
            raise Refused(f"item {item_id} is already closed ({item['status']}, {item['closed_how']})")
        t = now()
        # Rule 7.
        conn.execute("UPDATE items SET status=?, closed_how=?, closed_why=?, closed_at=?, updated_at=? "
                     "WHERE id=?", (STATUS_BY_HOW[how], how, why, t, t, item_id))
        _event(conn, "item_closed", actor, item_id=item_id, detail={"how": how, "why": why})
        return _item(conn, item_id)
    return _write(tx)


def update_item(item_id, *, actor=None, _action="item_updated", **fields):
    bad = set(fields) - set(UPDATABLE)
    if bad:
        raise ValueError(f"cannot update {sorted(bad)}; allowed: {UPDATABLE}")
    if "kind" in fields and fields["kind"] not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")

    def tx(conn):
        item = _item(conn, item_id)
        _guard_person(item["person"])
        new = dict(item, **fields)
        _entry_test(new["added_by"], new["waiting"], new["line"], new["action_label"], new["action_instruction"])
        _guard_closed(item["person"], *(fields.get(k) for k in ("line", "action_label", "action_instruction")))
        changes = {k: v for k, v in fields.items() if v != item[k]}
        if changes:
            conn.execute(f"UPDATE items SET {', '.join(k + '=?' for k in changes)}, updated_at=? WHERE id=?",
                         (*changes.values(), now(), item_id))
        _event(conn, _action, actor, item_id=item_id,
               detail={k: {"from": item[k], "to": v} for k, v in changes.items()})
        return _item(conn, item_id)
    return _write(tx)


def promote_item(item_id, actor=None):
    """someday -> needs_you."""
    return update_item(item_id, actor=actor, _action="item_promoted", kind="needs_you")


def attach_session(item_id, *, channel=None, thread_ts=None, session_id=None, session_is_shared=None,
                   status=None, actor=None):
    if status is not None and status not in OPEN:
        raise ValueError("attach can only set status open or working; use close_item to close")
    given = {"slack_channel": channel, "slack_thread_ts": thread_ts, "session_id": session_id,
             "session_is_shared": None if session_is_shared is None else int(bool(session_is_shared)),
             "status": status}

    def tx(conn):
        item = _item(conn, item_id)
        _guard_person(item["person"])
        if status and item["status"] not in OPEN:
            raise Refused(f"item {item_id} is closed; it cannot become {status}")
        changes = {k: v for k, v in given.items() if v is not None and v != item[k]}
        if changes:
            conn.execute(f"UPDATE items SET {', '.join(k + '=?' for k in changes)}, updated_at=? WHERE id=?",
                         (*changes.values(), now(), item_id))
        _event(conn, "session_attached", actor, item_id=item_id, detail=changes)
        return _item(conn, item_id)
    return _write(tx)


def mark_seen(item_id, actor=None):
    def tx(conn):
        item = _item(conn, item_id)
        _guard_person(item["person"])
        t = now()
        conn.execute("UPDATE items SET seen_at=?, updated_at=? WHERE id=?", (t, t, item_id))
        _event(conn, "item_seen", actor, item_id=item_id)
        return _item(conn, item_id)
    return _write(tx)


def list_items(person, *, status=OPEN, kind=None, department=None):
    sql, args = "SELECT * FROM items WHERE person=?", [person]
    if status:
        status = (status,) if isinstance(status, str) else tuple(status)
        sql += f" AND status IN ({','.join('?' * len(status))})"
        args += status
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if department:
        sql += " AND department=?"
        args.append(department)
    return _read(sql + " ORDER BY rank, waiting_since IS NULL, waiting_since, id", args)


def get_item(item_id):
    rows = _read("SELECT * FROM items WHERE id=?", (item_id,))
    if not rows:
        raise LookupError(f"no item {item_id}")
    return rows[0]


def recent_dismissals(person, days=30):
    cutoff = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="seconds")
    return _read("SELECT * FROM items WHERE person=? AND closed_how='dismissed' AND closed_at>=? "
                 "ORDER BY closed_at DESC", (person, cutoff))


# ---------- events ----------

def log_event(action, *, actor, item_id=None, run_id=None, detail=None):
    if isinstance(detail, str):
        json.loads(detail)  # detail is JSON; refuse garbage early
    if not action:
        raise ValueError("an event needs an action")

    def tx(conn):
        if item_id is not None:
            _guard_person(_item(conn, item_id)["person"])
        if run_id is not None:
            _guard_person(_run(conn, run_id)["person"])
        return _event(conn, action, actor, item_id=item_id, run_id=run_id, detail=detail)
    return _write(tx)


def events(item_id=None, run_id=None, action=None, since=None, limit=200):
    sql, args = "SELECT * FROM events WHERE 1=1", []
    for col, val, op in (("item_id", item_id, "="), ("run_id", run_id, "="), ("action", action, "="),
                         ("at", since, ">=")):
        if val is not None:
            sql += f" AND {col}{op}?"
            args.append(val)
    rows = _read(f"SELECT * FROM ({sql} ORDER BY id DESC LIMIT ?) ORDER BY id", args + [limit])
    for r in rows:
        if r["detail"]:
            try:
                r["detail"] = json.loads(r["detail"])
            except ValueError:
                pass
    return rows


# ---------- runs ----------

def _run(conn, run_id):
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise LookupError(f"no run {run_id}")
    return dict(row)


def start_run(department, person, *, model=None, effort=None, mode=None, actor=None):
    _check_person(person)
    _guard_person(person)

    def tx(conn):
        cur = conn.execute("INSERT INTO runs(department, person, model, effort, mode, started_at) "
                           "VALUES (?,?,?,?,?,?)", (department, person, model, effort, mode, now()))
        _event(conn, "run_started", actor, run_id=cur.lastrowid,
               detail={"department": department, "person": person, "model": model, "effort": effort, "mode": mode})
        return cur.lastrowid
    return _write(tx)


def finish_run(run_id, *, status, actor=None, **numbers):
    if status not in ("ok", "failed"):
        raise ValueError("status must be ok or failed")
    bad = set(numbers) - set(RUN_FIELDS)
    if bad:
        raise ValueError(f"unknown run fields {sorted(bad)}")
    numbers = {k: v for k, v in numbers.items() if v is not None}

    def tx(conn):
        run = _run(conn, run_id)
        _guard_person(run["person"])
        if run["status"] != "running":
            raise Refused(f"run {run_id} already finished ({run['status']})")
        t = now()
        if "seconds" not in numbers:
            numbers["seconds"] = int((datetime.fromisoformat(t) - datetime.fromisoformat(run["started_at"])).total_seconds())
        # Unless told, count this department's items added/closed for this person during the run.
        if "items_added" not in numbers:
            numbers["items_added"] = conn.execute(
                "SELECT COUNT(*) FROM items WHERE person=? AND department=? AND created_at>=?",
                (run["person"], run["department"], run["started_at"])).fetchone()[0]
        if "items_closed" not in numbers:
            numbers["items_closed"] = conn.execute(
                "SELECT COUNT(*) FROM items WHERE person=? AND department=? AND closed_at>=?",
                (run["person"], run["department"], run["started_at"])).fetchone()[0]
        fields = dict(numbers, status=status, finished_at=t)
        conn.execute(f"UPDATE runs SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
                     (*fields.values(), run_id))
        _event(conn, "run_finished", actor, run_id=run_id, detail=fields)
        return _run(conn, run_id)
    return _write(tx)


def numbers_from_result(path):
    """Read what `claude -p --output-format json` printed -> finish_run numbers."""
    with open(path) as f:
        d = json.load(f)
    usage = d.get("modelUsage") or {}
    parts = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}
    for m in usage.values():
        for k in parts:
            parts[k] += m.get(k) or 0
    out = {
        "tokens_in": parts["inputTokens"] + parts["cacheReadInputTokens"] + parts["cacheCreationInputTokens"],
        "tokens_out": parts["outputTokens"],
        "tokens_cache_read": parts["cacheReadInputTokens"],
        "tokens_cache_write": parts["cacheCreationInputTokens"],
        "subagents": (d.get("subagent_stats") or {}).get("spawned"),
        "cost_usd": d.get("total_cost_usd"),
        "session_id": d.get("session_id"),
    }
    if d.get("duration_ms") is not None:
        out["seconds"] = round(d["duration_ms"] / 1000)
    return out


def last_run(department=None, person=None):
    sql, args = "SELECT * FROM runs WHERE 1=1", []
    if department:
        sql += " AND department=?"
        args.append(department)
    if person:
        sql += " AND person=?"
        args.append(person)
    rows = _read(sql + " ORDER BY id DESC LIMIT 1", args)
    return rows[0] if rows else None


# ---------- preferences ----------

def get_pref(person, key):
    rows = _read("SELECT * FROM preferences WHERE person=? AND key=?", (person, key))
    return rows[0] if rows else None


def set_pref(person, key, value, quote=None, actor=None):
    _check_person(person)
    _guard_person(person)

    def tx(conn):
        old = conn.execute("SELECT value FROM preferences WHERE person=? AND key=?", (person, key)).fetchone()
        conn.execute("INSERT INTO preferences(person, key, value, quote, set_at) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(person, key) DO UPDATE SET value=excluded.value, quote=excluded.quote, "
                     "set_at=excluded.set_at", (person, key, value, quote, now()))
        _event(conn, "pref_set", actor, detail={"person": person, "key": key, "from": old[0] if old else None,
                                                "to": value, "quote": quote})
        return dict(conn.execute("SELECT * FROM preferences WHERE person=? AND key=?", (person, key)).fetchone())
    return _write(tx)


def list_prefs(person):
    return _read("SELECT * FROM preferences WHERE person=? ORDER BY key", (person,))
