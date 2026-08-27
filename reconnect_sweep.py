"""Reconnect backlog sweep — find out who tried to reach us while we were down.

Why this exists
---------------
The bot's local instruments only record what arrived while the process was
alive. audit.log and the session JSONLs are written by this process; when the
machine is off the network there is no process, so the messages people sent do
not fail loudly, they simply never appear anywhere on this disk. On restart the
bot therefore has a perfectly clean local record and no idea that anyone tried.

This happened: the machine came off the network for four days. A teammate sent
seven messages into their DM over that window, one of them with a file attached
and a direct "can you read this?", and got silence. When the process came back
it never looked. The only instrument that still had those messages was the
Slack API, and nothing was asking it.

So: on every startup, if we were down for longer than a normal restart, ask
Slack what arrived in the gap and tell each person who is still waiting. The
rule this encodes is that an outage ends when the people affected KNOW, not
when capacity comes back.

Design constraints
------------------
- Notify, don't replay. Stale requests are not re-executed; the person is told
  what we missed and their reply lands in a live session.
- Idempotent. Notified message timestamps are persisted, so a crash-loop
  cannot turn one backlog into ten notices.
- Silent on normal restarts. Deploys and restarts are frequent; below
  MIN_DOWNTIME_SECONDS this module does nothing at all.
- Bounded. Never reaches back further than MAX_LOOKBACK_DAYS.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger("bot.reconnect")

STATE_FILE = Path(__file__).parent / ".reconnect_state.json"

# A restart that takes less than this is a deploy, not an outage. Staying quiet
# here is the whole reason this can be left on by default.
MIN_DOWNTIME_SECONDS = 30 * 60

# Never look further back than this, however stale the watermark is.
MAX_LOOKBACK_DAYS = 14

# How often the liveness watermark is refreshed while running.
HEARTBEAT_SECONDS = 60

# Cap per sweep so a pathological state file cannot produce a wall of posts.
MAX_CONVERSATIONS_NOTIFIED = 25


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state))
    except OSError as exc:
        logger.warning(f"reconnect: could not write state: {exc}")


def last_seen() -> float | None:
    """Epoch seconds when this bot was last known to be alive, or None."""
    value = _load_state().get("last_seen")
    return float(value) if value else None


def touch(now: float | None = None) -> None:
    """Record that we are alive right now."""
    state = _load_state()
    state["last_seen"] = now if now is not None else time.time()
    _save_state(state)


def _notified() -> set[str]:
    return set(_load_state().get("notified", []))


def _remember_notified(message_ts: list[str]) -> None:
    state = _load_state()
    seen = state.get("notified", [])
    seen.extend(t for t in message_ts if t not in seen)
    # Keep the tail bounded; anything this old is outside MAX_LOOKBACK_DAYS.
    state["notified"] = seen[-500:]
    _save_state(state)


def heartbeat_loop(interval: int = HEARTBEAT_SECONDS) -> None:
    while True:
        touch()
        time.sleep(interval)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def downtime_seconds(now: float | None = None) -> float | None:
    """Seconds between the last recorded heartbeat and now.

    None when there is no watermark at all — a first run must not report the
    epoch as a four-decade outage.
    """
    seen = last_seen()
    if seen is None:
        return None
    return (now if now is not None else time.time()) - seen


def is_outage(gap: float | None) -> bool:
    return gap is not None and gap >= MIN_DOWNTIME_SECONDS


def unanswered_in(messages: list[dict], roster: set[str], already: set[str]) -> list[dict]:
    """Human messages in this conversation that nobody ever replied to.

    A bot reply lands in a thread, so reply_count == 0 is the signal that a
    message was never picked up. Messages authored by a bot, by someone off the
    roster, or already covered by a previous sweep are not backlog.
    """
    out = []
    for m in messages:
        if m.get("bot_id") or m.get("subtype"):
            continue
        user = m.get("user")
        if not user or user not in roster:
            continue
        if m.get("reply_count"):
            continue
        if m.get("ts") in already:
            continue
        out.append(m)
    return sorted(out, key=lambda m: float(m["ts"]))


def compose_notice(msgs: list[dict], gap_seconds: float) -> str:
    """The heads-up. Leads with the fact, names the cost, asks nothing."""
    hours = gap_seconds / 3600
    window = f"{hours:.0f} hours" if hours < 48 else f"{hours / 24:.0f} days"
    count = len(msgs)
    noun = "message" if count == 1 else "messages"
    lines = [
        f"I was offline for about {window} and missed {count} {noun} from you here — "
        f"that's on me to tell you, not on you to re-ask.",
    ]
    with_files = [m for m in msgs if m.get("files")]
    if with_files:
        names = ", ".join(
            f.get("name", "a file") for m in with_files for f in m.get("files", [])
        )
        lines.append(f"Including an attachment I never opened: {names}.")
    lines.append("I'm back now. Reply here and I'll pick it up.")
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def run_sweep(client, roster: set[str], gap_seconds: float, *, dry_run: bool = False,
              now: float | None = None) -> list[dict]:
    """Ask Slack what arrived while we were down. Returns the notices."""
    now = now if now is not None else time.time()
    oldest = max(now - gap_seconds, now - MAX_LOOKBACK_DAYS * 86400)
    already = _notified()
    notices: list[dict] = []

    cursor = None
    conversations = []
    while True:
        resp = client.conversations_list(
            types="im,mpim", limit=200, exclude_archived=True, cursor=cursor
        )
        conversations.extend(resp.get("channels", []))
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break

    # A sweep that scans nothing looks exactly like a sweep that found nothing.
    logger.info(f"reconnect: scanning {len(conversations)} conversations since {oldest:.0f}")
    if not conversations:
        logger.warning("reconnect: conversations.list returned nothing — not a clean result")
        return []

    for conv in conversations:
        if len(notices) >= MAX_CONVERSATIONS_NOTIFIED:
            logger.warning("reconnect: hit MAX_CONVERSATIONS_NOTIFIED, stopping early")
            break
        channel_id = conv.get("id")
        try:
            history = client.conversations_history(
                channel=channel_id, oldest=str(oldest), limit=200
            )
        except Exception as exc:  # noqa: BLE001 — one bad channel must not kill the sweep
            logger.warning(f"reconnect: history failed for {channel_id}: {exc}")
            continue

        missed = unanswered_in(history.get("messages", []), roster, already)
        if not missed:
            continue

        notice = {
            "channel": channel_id,
            "user": missed[0]["user"],
            "thread_ts": missed[0]["ts"],
            "count": len(missed),
            "text": compose_notice(missed, gap_seconds),
            "message_ts": [m["ts"] for m in missed],
        }
        notices.append(notice)

        if dry_run:
            continue
        try:
            client.chat_postMessage(
                channel=channel_id, text=notice["text"], thread_ts=notice["thread_ts"]
            )
            _remember_notified(notice["message_ts"])
            logger.info(
                f"reconnect: notified {notice['user']} in {channel_id} "
                f"about {notice['count']} missed messages"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"reconnect: could not post notice to {channel_id}: {exc}")

    return notices


def startup(client, roster: set[str]) -> None:
    """Read the watermark, then start the heartbeat, then sweep in background.

    Order matters: the heartbeat overwrites the watermark, so the gap has to be
    captured before it starts.
    """
    gap = downtime_seconds()
    threading.Thread(target=heartbeat_loop, daemon=True).start()

    if not is_outage(gap):
        logger.info(
            f"reconnect: no sweep (downtime "
            f"{'unknown — first run' if gap is None else f'{gap:.0f}s'} "
            f"< {MIN_DOWNTIME_SECONDS}s)"
        )
        return

    logger.info(f"reconnect: down for {gap / 3600:.1f}h — sweeping for missed messages")
    threading.Thread(
        target=lambda: run_sweep(client, roster, gap), daemon=True
    ).start()
