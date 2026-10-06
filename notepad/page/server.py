"""The notepad page: one page a person opens to unblock the people and agents waiting on them.

Every read and write goes through notepad.py; this file never touches the database directly.
Run: python3 page/server.py  (NOTEPAD_PAGE_PORT env, default 8950). See README.md.
"""
import ipaddress
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from flask import Flask, abort, jsonify, redirect, render_template, request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import notepad  # noqa: E402

# Call the bot directly on localhost, never through the tunnel: it refuses relayed requests.
BOT_ACT_URL = os.environ.get("BOT_ACT_URL", "http://127.0.0.1:3000/notepad/act")
SESSIONS_JSON = os.path.expanduser(os.environ.get("BOT_SESSIONS_JSON", "~/Projects/slack-bot/.sessions.json"))
# Extra names this page may be opened under, besides localhost and this machine's own name.
EXTRA_HOSTS = [h.strip().lower() for h in os.environ.get("NOTEPAD_PAGE_HOSTS", "").split(",") if h.strip()]
STALE_AFTER = timedelta(hours=26)
DOUBLE_TAP_WINDOW = timedelta(seconds=30)   # a second act within this window returns the first thread
EMAIL_EVENTS = ("email_archived", "email_would_archive")
ERROR_NOT_STARTED = "Could not start this. Nothing was changed."

app = Flask(__name__, template_folder=os.path.join(HERE, "templates"),
            static_folder=os.path.join(HERE, "static"))
_item_locks = {}
_locks_guard = threading.Lock()


# ---------- small helpers ----------

def _lock_for(item_id):
    with _locks_guard:
        return _item_locks.setdefault(item_id, threading.Lock())


def people():
    """{name: slack_user_id} from the notepad config, read fresh so an edit needs no restart."""
    return {name: (info or {}).get("slack_user_id") for name, info in (notepad.config().get("people") or {}).items()}


def _person_or_404(person):
    if person not in people():
        abort(404)
    return person


def assistant_name():
    return notepad.config().get("assistant_name") or "Your AI"


@app.context_processor
def _names():
    return {"assistant": assistant_name()}


def _caller_allowed(addr):
    """This machine or the tailnet (100.64.0.0/10). Not the home Wi-Fi."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip in ipaddress.ip_network("100.64.0.0/10") \
        or ip in ipaddress.ip_network("fd7a:115c:a1e0::/48")


def _host_allowed(host):
    name = (host or "").rsplit(":", 1)[0].strip("[]").lower()
    own = socket.gethostname().split(".")[0].lower()
    for ok in ["localhost", own, *EXTRA_HOSTS]:
        if name == ok or name.startswith(ok + "."):
            return True
    return _caller_allowed(name)


@app.before_request
def _guard():
    # A tap here starts a full-permission session, so the page answers only to this machine
    # and the tailnet, only under its own name, and never to a form posted by another site.
    if not _caller_allowed(request.remote_addr or ""):
        abort(403)
    if not _host_allowed(request.host):
        abort(403)
    if request.method == "POST":
        if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            abort(403)
        origin = request.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != request.host:
            abort(403)


def _actor(person):
    return f"page:{person}"


def _wants_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"


def _item_or_404(item_id):
    try:
        return notepad.get_item(item_id)
    except LookupError:
        abort(404)


def thread_url(channel, thread_ts):
    workspace = notepad.config().get("slack_workspace")   # the subdomain in <workspace>.slack.com
    if not (channel and thread_ts and workspace):
        return None
    return f"https://{workspace}.slack.com/archives/{channel}/p{thread_ts.replace('.', '')}"


def _parse_day(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parse_ts(s):
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.astimezone()
    except (TypeError, ValueError):
        return None


NUM_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]


def count_sentence(n):
    word = NUM_WORDS[n] if n < len(NUM_WORDS) else str(n)
    if n == 0:
        return "Nothing needs you."
    return f"{word} {'thing needs' if n == 1 else 'things need'} you."


def duration(seconds):
    if seconds is None:
        return None
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m} min {s:02d} s" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min"


def tokens(n):
    if n is None:
        return None
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k" if n >= 10_000 else f"{n / 1_000:.1f}k"
    return str(n)


def clock(ts):
    dt = _parse_ts(ts)
    return dt.strftime("%-I:%M %p").lower().replace(" ", " ") if dt else None


def day_label(d):
    return f"{d.day} {d.strftime('%b')}"


# ---------- the view model ----------

def card(item, person):
    """Everything the template needs for one item."""
    since = _parse_day(item["waiting_since"])
    days = (date.today() - since).days if since else None
    own = item["added_by"] == person and item["waiting"] == person
    return {
        **item,
        "own": own,
        "who": "You added this" if own else item["waiting"],
        "days": days,
        "since_label": day_label(since) if since else None,
        "wait_text": (None if days is None else "today" if days <= 0 else
                      "1 day" if days == 1 else f"{days} days"),
        "ticks": min(days or 0, 14),
        "ticks_more": (days or 0) > 14,
        "thread": thread_url(item["slack_channel"], item["slack_thread_ts"]),
    }


def _sessions_map():
    try:
        with open(SESSIONS_JSON) as f:     # read-only; the bot owns this file
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def adopt_thread_sessions(items, person):
    """A working item whose session is still the shared one gets its thread's own session,
    once the bot has saved it."""
    candidates = [i for i in items if i["status"] == "working" and i["slack_thread_ts"]
                  and (i["session_is_shared"] or not i["session_id"])]
    if not candidates:
        return items
    sessions = _sessions_map()
    out = []
    for i in items:
        own = sessions.get(i["slack_thread_ts"]) if i in candidates else None
        if own and own != i["session_id"]:
            try:
                i = notepad.attach_session(i["id"], session_id=own, session_is_shared=False, actor=_actor(person))
            except notepad.Refused as e:
                app.logger.warning("could not adopt session for item %s: %s", i["id"], e)
        out.append(i)
    return out


def run_status(run):
    """One plain line when the last run cannot be trusted, else None."""
    if not run:
        return None   # nothing records runs on this install; there is no run to be stale
    started = _parse_ts(run["started_at"])
    ended = _parse_ts(run["finished_at"]) or started
    if run["status"] == "running":
        return f"This morning's run started at {clock(run['started_at'])} and has not finished. These items are from before it."
    if run["status"] == "failed":
        return f"The last run failed at {clock(run['finished_at'] or run['started_at'])}. These items may be out of date."
    if ended and datetime.now().astimezone() - ended > STALE_AFTER:
        return f"The last run finished on {day_label(ended.date())}. These items may be out of date."
    return None


def footer(run):
    if not run:
        return None
    emails = []
    for e in notepad.events(run_id=run["id"], limit=500):
        if e["action"] in EMAIL_EVENTS:
            d = e["detail"] if isinstance(e["detail"], dict) else {}
            emails.append({"from": d.get("from") or "", "subject": d.get("subject") or "(no subject)",
                           "reason": d.get("reason") or "", "listed": e["action"] == "email_would_archive"})
    listed = any(m["listed"] for m in emails) or run.get("mode") == "list-only"
    count = len(emails) if emails else (run.get("emails_archived") or 0)
    started = _parse_ts(run["started_at"])
    return {
        "when": f"{started.strftime('%a')} {day_label(started.date())}, {clock(run['started_at'])}" if started else "",
        "status": run["status"],
        "time": duration(run.get("seconds")),
        "tokens_in": tokens(run.get("tokens_in")),
        "tokens_out": tokens(run.get("tokens_out")),
        "subagents": run.get("subagents"),
        "email_count": count,
        "email_verb": "listed for archiving" if listed else "archived",
        "emails": emails,
    }


@app.template_filter("tokens")
def _tokens_filter(n):
    return tokens(n)


# ---------- routes ----------

@app.get("/")
def root():
    names = list(people())
    if not names:
        return ("No people configured. Copy notepad/config.json.example to notepad/config.json "
                "and list who has a notepad.\n", 404, {"Content-Type": "text/plain"})
    return redirect(f"/{names[0]}")


@app.get("/health")
def health():
    try:
        notepad.last_run()
        return jsonify({"ok": True, "db": notepad.db_path()})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/<person>")
def page(person):
    _person_or_404(person)
    items = [i for i in notepad.list_items(person) if i["kind"] == "needs_you"]
    items = adopt_thread_sessions(items, person)
    cards = [card(i, person) for i in items]
    needs = [c for c in cards if c["status"] == "open" and not c["seen_at"]]
    read = [c for c in cards if c["status"] == "open" and c["seen_at"]]
    working = [c for c in cards if c["status"] == "working"]
    run = notepad.last_run(person=person)
    today = date.today()
    return render_template(
        "page.html", person=person, name=person.capitalize(),
        today=f"{today.strftime('%A')}, {today.day} {today.strftime('%B')}",
        sentence=count_sentence(len(needs) + len(read)),
        needs=needs, read=read, working=working,
        warning=run_status(run), run=footer(run), run_clock=clock(run["finished_at"]) if run and not run_status(run) else None,
    )


@app.post("/<person>/items")
def add(person):
    _person_or_404(person)
    line = " ".join((request.form.get("line") or (request.get_json(silent=True) or {}).get("line") or "").split())
    if not line:
        return _reply(person, False, "Write one line first.", 400)
    if len(line) > 500:
        return _reply(person, False, "Keep it to one line, under 500 characters.", 400)
    try:
        item = notepad.add_item(person, line, added_by=person, actor=_actor(person))
    except notepad.Refused as e:
        return _reply(person, False, f"Not added. {e}", 409)
    html = render_template("_card.html", c=card(item, person), section="needs")
    return _reply(person, True, None, 200, id=item["id"], html=html)


@app.post("/items/<int:item_id>/handled")
def handled(item_id):
    return _close(item_id, "handled")


@app.post("/items/<int:item_id>/dismiss")
def dismiss(item_id):
    return _close(item_id, "dismissed")


def _close(item_id, how):
    item = _item_or_404(item_id)
    person = item["person"]
    try:
        notepad.close_item(item_id, how, why="from the notepad page", actor=_actor(person))
    except notepad.Refused as e:
        # already closed (for example a double tap): the outcome they asked for already holds
        if item["status"] in ("open", "working"):
            return _reply(person, False, str(e), 409)
    return _reply(person, True, None, 200, id=item_id, how=how)


@app.post("/items/<int:item_id>/seen")
def seen(item_id):
    item = _item_or_404(item_id)
    # a tap can close the item inside the one-second seen timer; a closed item is not "seen"
    if not item["seen_at"] and item["status"] in ("open", "working"):
        notepad.mark_seen(item_id, actor=_actor(item["person"]))
    return jsonify({"ok": True})


@app.post("/items/<int:item_id>/act")
def act(item_id):
    item = _item_or_404(item_id)
    person = item["person"]
    actor = _actor(person)
    body = request.get_json(silent=True) or {}
    typed = " ".join((request.form.get("text") or body.get("text") or "").split())
    if item["status"] not in ("open", "working"):
        return _reply(person, False, "This item is already closed.", 409)
    instruction = typed or (item["action_instruction"] or "").strip()
    if not instruction:
        return _reply(person, False, f"Write what {assistant_name()} should do first.", 400)

    lock = _lock_for(item_id)
    if not lock.acquire(blocking=False):
        # the first tap is still talking to the bot; it will answer for both
        return _reply(person, False, "Already starting.", 409, busy=True)
    try:
        item = notepad.get_item(item_id)
        recent = _recent_start(item_id)
        if recent and item["slack_thread_ts"]:
            notepad.log_event("act_repeat_ignored", actor=actor, item_id=item_id,
                              detail={"first_at": recent["at"], "typed": bool(typed)})
            return _reply(person, True, None, 200, id=item_id, started=True, repeat=True,
                          thread=thread_url(item["slack_channel"], item["slack_thread_ts"]))

        user_id = people().get(person)
        if not user_id:
            return _reply(person, False, f"No slack_user_id for {person} in the notepad config.", 409)
        payload = {
            "user_id": user_id, "item_id": item_id,
            "instruction": f"Item {item_id}. {item['waiting']} is waiting: {item['line']}\n\n{instruction}",
            "anchor_text": f"{item['waiting']}: {item['line']}",
            "thread_ts": None, "channel": None, "session_id": None, "fork": False, "dry_run": False,
        }
        if item["slack_thread_ts"]:
            # If the thread never saved a session of its own, the item still holds the job's
            # shared one. It must be forked, never resumed: other items share it.
            payload.update(thread_ts=item["slack_thread_ts"], channel=item["slack_channel"],
                           session_id=item["session_id"], fork=bool(item["session_is_shared"]))
        elif item["session_id"] and item["session_is_shared"]:
            payload.update(session_id=item["session_id"], fork=True)
        elif item["session_id"]:
            payload.update(session_id=item["session_id"], fork=False)

        result, error = _call_bot(payload)
        if error:
            notepad.log_event("act_failed", actor=actor, item_id=item_id,
                              detail={"error": error, "typed": bool(typed), "bot_url": BOT_ACT_URL})
            return _reply(person, False, ERROR_NOT_STARTED, 502)

        if (item["slack_channel"], item["slack_thread_ts"], item["status"]) != (
                result["channel"], result["thread_ts"], "working"):
            notepad.attach_session(item_id, channel=result["channel"], thread_ts=result["thread_ts"],
                                   status="working", actor=actor)
        notepad.log_event("act_started", actor=actor, item_id=item_id,
                          detail={"mode": result.get("mode"), "typed": bool(typed), "fork": payload["fork"],
                                  "instruction": instruction[:500]})
        return _reply(person, True, None, 200, id=item_id, started=True,
                      thread=thread_url(result["channel"], result["thread_ts"]))
    finally:
        lock.release()


def _recent_start(item_id):
    for e in reversed(notepad.events(item_id=item_id, action="act_started", limit=1)):
        at = _parse_ts(e["at"])
        if at and datetime.now().astimezone() - at < DOUBLE_TAP_WINDOW:
            return e
    return None


def _call_bot(payload):
    """-> (result, None) on success, (None, reason) on any failure."""
    req = urllib.request.Request(BOT_ACT_URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read() or b"{}").get("error")
        except ValueError:
            detail = None
        return None, f"bot answered {e.code}: {detail or e.reason}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, f"bot unreachable: {e}"
    if not (isinstance(data, dict) and data.get("ok") and data.get("channel") and data.get("thread_ts")):
        return None, f"bot answered without a thread: {str(data)[:200]}"
    return data, None


def _reply(person, ok, error, code, **extra):
    if _wants_json():
        return jsonify({"ok": ok, "error": error, **extra}), code
    return redirect(f"/{person}", code=303)


if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("NOTEPAD_PAGE_PORT", "8950"))
    print(f"notepad page on 0.0.0.0:{port}, db {notepad.db_path()}, bot {BOT_ACT_URL}", flush=True)
    serve(app, host="0.0.0.0", port=port, threads=8)
