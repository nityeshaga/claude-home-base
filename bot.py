#!/usr/bin/env python3
"""
Your AI Employee — Slack bot powered by Claude Code.

HTTP Events API version (production-standard). Uses Flask + Cloudflare Tunnel
instead of Socket Mode. Slack sends stateless HTTP POSTs to your public URL.

Key difference from Socket Mode: Slack requires a 200 response within 3 seconds.
Claude Code calls take minutes, so we respond immediately and process in a
background thread, posting the result when ready.

Also supports proactive messaging via CLI:
    python bot.py --send USER_ID "message"
    python bot.py --channel "#general" "message"
    echo '{"result":"..."}' | python bot.py --send-result USER_ID
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot")

_rotating_handler = logging.handlers.RotatingFileHandler(
    LOG_DIR / "bot.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_rotating_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
logger.addHandler(_rotating_handler)

AUDIT_LOG = LOG_DIR / "audit.log"
audit_handler = logging.FileHandler(AUDIT_LOG, encoding="utf-8")
audit_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
audit_logger = logging.getLogger("bot.audit")
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
AUTHORIZED_USERS = set(
    u.strip() for u in os.environ.get("AUTHORIZED_USERS", "").split(",") if u.strip()
)
ALLOWED_CHANNEL_PREFIXES = ("consulting",)
PROJECT_DIR = os.environ.get("PROJECT_DIR", "")
if not PROJECT_DIR:
    logger.error("PROJECT_DIR not set. Add it to .env")
    raise SystemExit(1)

CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "7200"))  # 2 hour default

# Ring 1 users get --dangerously-skip-permissions; everyone else gets --permission-mode dontAsk
RING_1_USERS = {"U0AH2TTHDK8", "U0AH8J541RA", "U0AH9KM0PE1"}  # Nityesh, Natalia, Mike

# Ring 2+ restrictions — passed via --disallowedTools at spawn time
RING_2_DISALLOWED_TOOLS = [
    "Bash(gws-nityesh *)",
    "Bash(gws gmail +send *)",
    "Bash(gws gmail +reply *)",
    "Bash(gws gmail +reply-all *)",
    "Bash(gws gmail +forward *)",
    "Bash(gws gmail users messages send *)",
    "Bash(gws gmail users drafts send *)",
    "Bash(gws gmail users drafts create *)",
    "mcp__google-workspace",
    "Edit(//Users/claudie/CLAUDE.md)",
    "Edit(//Users/claudie/identity.md)",
    "Edit(//Users/claudie/about-you-and-how-you-came-to-life.md)",
    "Edit(//Users/claudie/teammates/teammates-access.md)",
    "Edit(//Users/claudie/.claude/**)",
    "Write(//Users/claudie/CLAUDE.md)",
    "Write(//Users/claudie/identity.md)",
    "Write(//Users/claudie/about-you-and-how-you-came-to-life.md)",
    "Write(//Users/claudie/teammates/teammates-access.md)",
    "Write(//Users/claudie/.claude/**)",
    "Read(//Users/claudie/.claude/projects/**/*.jsonl)",
    "Read(//Users/claudie/.claude/settings*)",
    "Bash(launchctl *)",
    "Bash(crontab *)",
]

RING_2_ALLOWED_TOOLS = [
    "Read", "Edit", "Write", "Grep", "Glob", "Bash",
    "WebSearch", "WebFetch", "Agent",
]
MAX_SLACK_MSG_LEN = 3900
PORT = int(os.environ.get("PORT", "3000"))

# Channels routed through the Codex harness instead of Claude.
# Gated entirely on channel ID; all other channels use the Claude path
# unchanged. Reversible by clearing this set.
CODEX_CHANNEL_IDS = {
    "C0B7CTYDD8Q",  # #claudie-codex
}
import bot_codex  # noqa: E402 — module-level import is fine, lazy not needed

# Streaming filter for content-free heartbeat blocks ("Holding for the remaining
# 3 batches.") — see narration_filter.py for the incident history and the
# 63-case both-directions suite. Imported DEFENSIVELY on purpose: this is a
# message-quality nicety, and the bot going dark is a far worse failure than one
# extra Slack message, so an import problem degrades to no-filtering.
try:
    from narration_filter import is_content_free_holding  # noqa: E402
except Exception as _nf_err:  # pragma: no cover — degraded path
    logger.warning(f"narration_filter unavailable, holding filter OFF: {_nf_err}")

    def is_content_free_holding(_text_block: str) -> bool:
        return False

# The Slack user ID of this bot — set via BOT_USER_ID env var.
# Used to identify the bot's own messages in thread history and to prevent
# duplicate handling of @mentions. Find it in your Slack app settings or
# by calling auth.test.
BOT_USER_ID = os.environ.get("BOT_USER_ID", "")

# Display name for the bot (used in thread context formatting)
BOT_DISPLAY_NAME = os.environ.get("BOT_DISPLAY_NAME", "Your AI Employee")

# ---------------------------------------------------------------------------
# Slack app (with signing secret for request verification)
# ---------------------------------------------------------------------------

app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# Cache for Slack user display names (user_id → display name)
_user_name_cache: dict[str, str] = {}

# Cache for Slack channel names (channel_id → channel name)
_channel_name_cache: dict[str, str] = {}


def _get_channel_name(channel_id: str) -> str:
    """Look up a Slack channel's name, with caching."""
    if channel_id in _channel_name_cache:
        return _channel_name_cache[channel_id]
    try:
        info = slack_client.conversations_info(channel=channel_id)
        name = info["channel"].get("name", channel_id)
        _channel_name_cache[channel_id] = name
    except Exception:
        name = channel_id
        _channel_name_cache[channel_id] = name
    return name


def _get_user_name(user_id: str) -> str:
    """Look up a Slack user's display name, with caching."""
    if user_id in _user_name_cache:
        return _user_name_cache[user_id]
    try:
        info = slack_client.users_info(user=user_id)
        profile = info["user"].get("profile", {})
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or info["user"].get("real_name")
            or user_id
        )
        _user_name_cache[user_id] = name
    except Exception:
        name = user_id
        _user_name_cache[user_id] = name
    return name



def _fetch_thread_context(channel: str, thread_ts: str, current_msg_ts: str) -> str | None:
    """Fetch all prior messages in a thread and format them as context for Claude.

    Returns a formatted string of the conversation history, or None if there's
    nothing useful (e.g., the thread has only the current message).
    Excludes the current message (it's already in the prompt) and bot messages
    that are Claude's own responses (to avoid echoing back our own output).
    """
    try:
        result = slack_client.conversations_replies(
            channel=channel, ts=thread_ts, limit=50,
        )
        messages = result.get("messages", [])
    except Exception as e:
        logger.warning(f"Failed to fetch thread history: {e}")
        return None

    if len(messages) <= 1:
        return None

    lines = []
    for msg in messages:
        msg_ts = msg.get("ts", "")
        # Skip the current inbound message — it's already the prompt
        if msg_ts == current_msg_ts:
            continue

        msg_user = msg.get("user", "")
        msg_text = msg.get("text", "").strip()
        if not msg_text:
            continue

        if msg_user == BOT_USER_ID:
            lines.append(f"[You ({BOT_DISPLAY_NAME})]:\n{msg_text}")
        else:
            name = _get_user_name(msg_user)
            lines.append(f"[{name}]({msg_user}):\n{msg_text}")

    if not lines:
        return None

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Session store: thread_ts → Claude session_id (file-backed)
# ---------------------------------------------------------------------------

SESSION_FILE = LOG_DIR / ".sessions.json"
MAX_SESSIONS = 200
_session_file_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Forward map: DM thread_ts → original thread for cross-thread routing
# ---------------------------------------------------------------------------

FORWARDS_FILE = LOG_DIR / ".forwards.json"
FORWARD_TTL = 14 * 86400  # 14 days
_forwards_file_lock = threading.Lock()


def _load_forwards() -> dict:
    try:
        return json.loads(FORWARDS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _add_forward(dm_thread_ts: str, target_thread: str, target_channel: str,
                 session_id: str, user_id: str) -> None:
    with _forwards_file_lock:
        forwards = _load_forwards()
        forwards[dm_thread_ts] = {
            "thread": target_thread,
            "channel": target_channel,
            "session_id": session_id,
            "user_id": user_id,
            "registered_at": time.time(),
        }
        FORWARDS_FILE.write_text(json.dumps(forwards))


def _get_forward(dm_thread_ts: str) -> dict | None:
    return _load_forwards().get(dm_thread_ts)


def _remove_forward(dm_thread_ts: str) -> None:
    with _forwards_file_lock:
        forwards = _load_forwards()
        forwards.pop(dm_thread_ts, None)
        FORWARDS_FILE.write_text(json.dumps(forwards))


def _gc_forwards() -> None:
    with _forwards_file_lock:
        forwards = _load_forwards()
        now = time.time()
        expired = [k for k, v in forwards.items()
                   if now - v.get("registered_at", 0) > FORWARD_TTL]
        if expired:
            for k in expired:
                del forwards[k]
            FORWARDS_FILE.write_text(json.dumps(forwards))
            logger.info(f"GC'd {len(expired)} expired forward entries")


def _load_sessions() -> dict:
    try:
        return json.loads(SESSION_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_session(thread_ts: str, session_id: str) -> None:
    with _session_file_lock:
        sessions = _load_sessions()
        sessions[thread_ts] = session_id
        if len(sessions) > MAX_SESSIONS:
            for key in sorted(sessions.keys())[:-MAX_SESSIONS]:
                del sessions[key]
        SESSION_FILE.write_text(json.dumps(sessions))


def _get_session(thread_ts: str) -> str | None:
    return _load_sessions().get(thread_ts)


# ---------------------------------------------------------------------------
# Live session management: long-lived Claude processes with stream-json I/O
#
# Instead of spawning a new `claude -p` subprocess for every message (which
# causes race conditions when multiple messages arrive for the same thread),
# we keep Claude processes alive and pipe messages to their stdin as JSON.
# The CLI queues them automatically, matching terminal behavior.
# ---------------------------------------------------------------------------

IDLE_TIMEOUT = 10800  # 3 hours — kill process if no messages


@dataclass
class LiveSession:
    """A long-lived Claude CLI process attached to a Slack thread."""
    proc: subprocess.Popen
    session_id: str | None = None
    stdin_lock: threading.Lock = field(default_factory=threading.Lock)
    last_activity: float = field(default_factory=time.time)
    channel: str = ""
    thread_ts: str = ""
    user_id: str = ""
    # Serializes the full send→wait cycle so only one message at a time
    # is being actively processed. Other messages queue in our Python code.
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    # Callback for posting text blocks to Slack
    _on_text: callable = field(default=None, repr=False)
    # Event that signals when a turn (result) is complete
    _turn_done: threading.Event = field(default_factory=threading.Event)
    # Eyes reactions from mid-turn steering messages, removed by the reader
    # loop when the absorbing turn's result arrives. CPython list append/pop
    # are atomic, so no extra lock for this traffic.
    pending_reactions: list = field(default_factory=list)
    # Highest 100k context threshold already announced in the thread
    ctx_notified_level: int = 0


# thread_ts → LiveSession
_live_sessions: dict[str, LiveSession] = {}
_live_sessions_lock = threading.Lock()


# Parallel registry for Codex sessions (CODEX_CHANNEL_IDS only).
# Kept fully separate from _live_sessions so the two harnesses cannot
# interfere with each other.
_codex_sessions: dict[str, "bot_codex.CodexSession"] = {}
_codex_sessions_lock = threading.Lock()


def _get_or_create_codex_session(thread_ts: str, channel: str, user_id: str,
                                 on_text, on_status=None) -> "bot_codex.CodexSession":
    """Get an existing Codex session for this Slack thread or spawn a fresh one.

    Mirrors _get_or_create_live_session but routes through bot_codex.
    """
    with _codex_sessions_lock:
        existing = _codex_sessions.get(thread_ts)
        if existing and existing.proc.poll() is None:
            existing.last_activity = time.time()
            existing._on_text = on_text
            existing._on_status = on_status
            return existing
        session = bot_codex.spawn_codex_session(
            thread_ts=thread_ts, channel=channel, user_id=user_id,
            on_text=on_text, on_status=on_status,
        )
        _codex_sessions[thread_ts] = session
        return session


def _get_trust_battery_context() -> str:
    """Read all trust battery JSON files and format a context summary."""
    battery_dir = Path.home() / "trust-battery"
    if not battery_dir.exists():
        return ""
    tiers = [
        (0, 25, "Propose and Wait"),
        (25, 50, "Routine Execution"),
        (50, 75, "Judgment Calls"),
        (75, 100, "Full Autonomy"),
    ]
    lines = ["## Trust Battery — Current State"]
    for name in ["nityesh", "natalia", "mike", "brooker"]:
        fpath = battery_dir / f"{name}.json"
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text())
            charge = data.get("current_charge", 0)
            last_updated = data.get("last_updated", "unknown")
            last_delta = 0.0
            if data.get("history"):
                last_delta = data["history"][-1].get("delta", 0.0)
            tier = next((t for lo, hi, t in tiers if lo <= charge < hi), "Full Autonomy")
            sign = "+" if last_delta >= 0 else ""
            lines.append(f"- {name.capitalize()}: {charge:.1f}% ({tier}) | Last: {sign}{last_delta:.1f} on {last_updated}")
        except Exception:
            continue
    if len(lines) == 1:
        return ""
    lines.append("")
    lines.append("Your autonomy level is determined by the battery charge for the")
    lines.append("team member you're interacting with:")
    lines.append("  0-25%  = Propose and Wait")
    lines.append("  25-50% = Routine Execution")
    lines.append("  50-75% = Judgment Calls")
    lines.append("  75-100% = Full Autonomy")
    return "\n".join(lines)


def _spawn_claude_process(session_id: str | None = None, user_id: str = "",
                          thread_ts: str = "", channel: str = "") -> subprocess.Popen:
    """Spawn a long-lived Claude CLI process with stream-json I/O."""
    battery_context = _get_trust_battery_context()
    cmd = [
        "claude",
        "-p", battery_context,
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--model", "claude-opus-4-8[1m]",
        "--effort", "high",
    ]
    if user_id in RING_1_USERS:
        cmd.extend(["--permission-mode", "bypassPermissions"])
    else:
        cmd.extend(["--permission-mode", "dontAsk"])
        cmd.extend(["--allowedTools", " ".join(RING_2_ALLOWED_TOOLS)])
        cmd.extend(["--disallowedTools", " ".join(RING_2_DISALLOWED_TOOLS)])
    if session_id:
        cmd.extend(["--resume", session_id])

    stderr_tmp = tempfile.NamedTemporaryFile(
        mode="w+", suffix=".stderr", delete=False
    )

    proc_env = {
        **os.environ,
        "CLAUDE_THREAD_TS": thread_ts,
        "CLAUDE_CHANNEL_ID": channel,
        "CLAUDE_SESSION_ID": session_id or "",
    }

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_tmp,
        text=True,
        cwd=PROJECT_DIR,
        env=proc_env,
    )
    perm_mode = "bypassPermissions" if user_id in RING_1_USERS else "dontAsk"
    logger.info(f"Spawned Claude process pid={proc.pid} (resume={session_id or 'none'}, user={user_id}, permissions={perm_mode})")
    return proc


# Context-utilization notices: announce each new 100k threshold in the thread
# as a small grey context block. Bot-side only — never enters Claude's context.
CTX_NOTIFY_STEP = 100_000
CTX_WINDOW = 1_000_000  # claude-opus-4-8[1m]


def _post_context_notice(session: LiveSession, ctx: int) -> None:
    """Post a small grey context-block notice about context utilization."""
    try:
        note = f"context window: ~{ctx / 1000:.0f}k of {CTX_WINDOW // 1000}k tokens ({ctx / CTX_WINDOW:.0%})"
        slack_client.chat_postMessage(
            channel=session.channel, thread_ts=session.thread_ts,
            text=note,
            blocks=[{"type": "context", "elements": [
                {"type": "mrkdwn", "text": f":brain: _{note}_"}]}],
        )
    except Exception as e:
        logger.warning(f"Failed to post context notice: {e}")


def _post_skill_notice(session: LiveSession, skill: str, args_str: str) -> None:
    """Post a small grey context-block notice that a skill was invoked."""
    try:
        note = f"skill: {skill}" + (f" · {args_str}" if args_str else "")
        slack_client.chat_postMessage(
            channel=session.channel, thread_ts=session.thread_ts,
            text=note,
            blocks=[{"type": "context", "elements": [
                {"type": "mrkdwn", "text": f":toolbox: _{note}_"}]}],
        )
    except Exception as e:
        logger.warning(f"Failed to post skill notice: {e}")


def _track_context(session: LiveSession, data: dict) -> None:
    """Watch usage on assistant events; announce each new 100k threshold.

    Context shrinks when the CLI compacts the conversation — re-arm the
    thresholds then, so utilization gets re-announced on the way back up.
    """
    # Subagent (Task) events stream through the same stdout with the
    # subagent's own, much smaller context — counting them re-arms the
    # threshold and re-fires the alert every turn. Main-loop events only.
    if data.get("parent_tool_use_id"):
        return
    usage = data.get("message", {}).get("usage") or {}
    ctx = (usage.get("input_tokens", 0)
           + usage.get("cache_read_input_tokens", 0)
           + usage.get("cache_creation_input_tokens", 0))
    if not ctx:
        return
    level = ctx // CTX_NOTIFY_STEP
    if level > session.ctx_notified_level:
        session.ctx_notified_level = level
        _post_context_notice(session, ctx)
    elif level < session.ctx_notified_level:
        session.ctx_notified_level = level


def _reader_loop(session: LiveSession) -> None:
    """Read stdout from a live Claude process and post responses to Slack.

    Runs in a dedicated thread for each live session.
    """
    try:
        for line in session.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Any output means the session is working — keep the idle reaper
            # away even when no new message has arrived for a long time
            # (e.g. a quiet multi-hour background workflow).
            session.last_activity = time.time()

            msg_type = data.get("type")

            if msg_type == "system":
                sid = data.get("session_id")
                if sid:
                    session.session_id = sid

            elif msg_type == "assistant":
                _track_context(session, data)
                content = data.get("message", {}).get("content", [])
                for block in content:
                    # Skill visibility: announce main-loop skill invocations in a
                    # grey context block (bot-side only, never enters Claude's
                    # context). Subagent skill calls are skipped to avoid noise.
                    if (isinstance(block, dict) and block.get("type") == "tool_use"
                            and block.get("name") == "Skill"
                            and not data.get("parent_tool_use_id")):
                        inp = block.get("input") or {}
                        args_str = str(inp.get("args") or "")[:120]
                        _post_skill_notice(session, inp.get("skill", "?"), args_str)
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and session._on_text:
                            session._on_text(text)

            elif msg_type == "result":
                sid = data.get("session_id")
                if sid:
                    session.session_id = sid
                    _save_session(session.thread_ts, sid)
                # Clear eyes reactions from steering messages this turn absorbed
                while session.pending_reactions:
                    ch, ts = session.pending_reactions.pop(0)
                    try:
                        slack_client.reactions_remove(channel=ch, name="eyes", timestamp=ts)
                    except Exception:
                        pass
                session._turn_done.set()

    except Exception as e:
        logger.error(f"Reader loop error for thread {session.thread_ts}: {e}")
    finally:
        # Process ended — unblock any thread waiting on a response
        session._turn_done.set()
        logger.info(f"Reader loop ended for thread {session.thread_ts} (pid={session.proc.pid})")
        with _live_sessions_lock:
            _live_sessions.pop(session.thread_ts, None)


def _get_or_create_live_session(thread_ts: str, channel: str, user_id: str = "") -> LiveSession:
    """Get an existing live session or create a new one for a thread."""
    with _live_sessions_lock:
        session = _live_sessions.get(thread_ts)
        if session and session.proc.poll() is None:
            session.last_activity = time.time()
            return session

        saved_session_id = _get_session(thread_ts)
        proc = _spawn_claude_process(session_id=saved_session_id, user_id=user_id,
                                     thread_ts=thread_ts, channel=channel)
        session = LiveSession(
            proc=proc,
            session_id=saved_session_id,
            channel=channel,
            thread_ts=thread_ts,
            user_id=user_id,
        )
        _live_sessions[thread_ts] = session

        threading.Thread(target=_reader_loop, args=(session,), daemon=True).start()
        return session


def _send_to_claude(session: LiveSession, text: str) -> None:
    """Send a user message to a live Claude process via stdin."""
    msg = json.dumps({
        "type": "user",
        "session_id": "",
        "message": {"role": "user", "content": text},
        "parent_tool_use_id": None,
    })
    with session.stdin_lock:
        session.proc.stdin.write(msg + "\n")
        session.proc.stdin.flush()
    session.last_activity = time.time()


def _cleanup_idle_sessions() -> None:
    """Periodically kill Claude processes that have been idle too long."""
    while True:
        time.sleep(300)
        now = time.time()
        to_remove = []
        with _live_sessions_lock:
            for ts, session in list(_live_sessions.items()):
                if now - session.last_activity > IDLE_TIMEOUT:
                    to_remove.append((ts, session))

        for ts, session in to_remove:
            logger.info(f"Cleaning up idle session for thread {ts} (pid={session.proc.pid})")
            try:
                session.proc.stdin.close()
                session.proc.wait(timeout=15)
            except Exception:
                session.proc.kill()
            if session.session_id:
                _save_session(ts, session.session_id)
            with _live_sessions_lock:
                _live_sessions.pop(ts, None)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def is_authorized(user_id: str) -> bool:
    return not AUTHORIZED_USERS or user_id in AUTHORIZED_USERS


def _audit_user_id(event: dict) -> str:
    """Slack puts the user id in different places depending on payload type:
    a plain string on message events, a nested dict on block_actions bodies.
    Reading only `event["user"]` logged `USER:{'id': 'U…'}` for button clicks."""
    user = event.get("user", "unknown")
    if isinstance(user, dict):
        return user.get("id", "unknown")
    return user


def log_unlisted_user(event: dict, outcome: str) -> None:
    """Record a message from someone outside AUTHORIZED_USERS.

    `outcome` is REQUIRED and is the whole point of this function. AUTHORIZED_USERS
    holds only the three Ring 1 names, so every Ring 2 teammate — who is fully
    entitled to be served in a channel, and IS served — used to be written to the
    audit log with the single label "UNAUTHORIZED". On 2026-08-16 that made 38 of
    the day's 60 audit lines read as rejections when nothing had been rejected,
    and the battery judge reasons off this file nightly. The behaviour was always
    correct; only the record was wrong.

    REFUSED  — a DM from an unlisted user: not answered.
    SERVED   — a channel message from an unlisted user: answered normally.
    """
    audit_logger.warning(
        f'UNLISTED_USER:{outcome} | USER:{_audit_user_id(event)} '
        f'| CHANNEL:{event.get("channel", "unknown")} '
        f'| MSG:"{event.get("text", "")[:100]}"'
    )


def log_ignored_channel(event: dict, reason: str) -> None:
    """Record a message dropped because its channel is outside
    ALLOWED_CHANNEL_PREFIXES.

    This path used to `return` before any audit write, and log_unlisted_user
    never fired for a Ring 1 name — so the one class of message that left ZERO
    trace in audit.log was an AUTHORIZED supervisor posting in a non-allowed
    channel. Mike's 2026-08-16 17:02 post in #every-one produced one bot.log
    line and nothing here, while Dan Shipper's three minutes later produced two,
    purely because Dan is not in AUTHORIZED_USERS. The log was blind in exactly
    the inverted spot, so "audit.log was empty" was a claim about the logging
    rather than about the room.

    Ignoring is CORRECT behaviour — the channel is ignore-by-design. This only
    makes the silence legible.
    """
    audit_logger.info(
        f'IGNORED_CHANNEL:{reason} | USER:{_audit_user_id(event)} '
        f'| CHANNEL:{event.get("channel", "unknown")} '
        f'| MSG:"{event.get("text", "")[:100]}"'
    )


def audit_interaction(
    event: dict, response_text: str, duration: float, session_id: str | None
) -> None:
    user = event.get("user", "unknown")
    channel = event.get("channel", "unknown")
    text = event.get("text", "")[:200]
    audit_logger.info(
        f"USER:{user} | CHANNEL:{channel} | SESSION:{session_id or 'new'} "
        f"| DURATION:{duration:.1f}s | MSG_LEN:{len(text)} | RESP_LEN:{len(response_text)} "
        f'| MSG:"{text}"'
    )


# ---------------------------------------------------------------------------
# Claude CLI (uses long-lived processes with stream-json I/O — see above)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Markdown → Slack mrkdwn
# ---------------------------------------------------------------------------


# Emphasis markers touching a URL break Slack's auto-linkification: `*https://x*`
# renders as literal asterisks around dead text, so the link is not clickable.
# This is a hard invariant with no judgment in it — a share link is often the
# whole deliverable — so it is enforced here rather than left to a memory file.
# Natalia has corrected it twice ("stop delivering links with * * at the start
# and end, that breaks the link" — 2026-08-11).
_LINK_EMPHASIS_PATTERNS = (
    # **<url>** / *<url>* / __<url>__ / _<url>_ / ~~<url>~~  (bare or <>-wrapped).
    # The URL match is non-greedy and the closing marker must not be followed by a
    # word character, so underscores *inside* a URL don't terminate the match early.
    (re.compile(r"(?<!\w)(\*\*|\*|__|_|~~|~)\s*(<?https?://[^\s<>*~]+?>?)\s*\1(?!\w)"), r"\2"),
    # **[label](url)** — bold around a markdown link breaks it the same way
    (re.compile(r"(?<!\w)(\*\*|\*|__|_)\s*(\[[^\]\n]+\]\([^)\s]+\))\s*\1(?!\w)"), r"\2"),
)


def strip_link_emphasis(text: str) -> str:
    """Remove bold/italic/strike markers wrapping a URL or markdown link.

    Applied to every outbound message so no URL can leave with emphasis
    characters glued to it, whatever the model wrote upstream.
    """
    for pattern, repl in _LINK_EMPHASIS_PATTERNS:
        prev = None
        while prev != text:  # nested markers, e.g. **_url_**
            prev = text
            text = pattern.sub(repl, text)
    return text


def md_to_slack(text: str) -> str:
    """Convert GitHub-flavored markdown to Slack mrkdwn."""
    text = strip_link_emphasis(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)
    text = re.sub(r"```\w*\n", "```\n", text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    return text


def chunk_message(text: str) -> list:
    """Split a message into Slack-safe chunks."""
    if len(text) <= MAX_SLACK_MSG_LEN:
        return [text]

    chunks = []
    while text:
        if len(text) <= MAX_SLACK_MSG_LEN:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, MAX_SLACK_MSG_LEN)
        if split_at == -1:
            split_at = text.rfind(" ", 0, MAX_SLACK_MSG_LEN)
        if split_at == -1:
            split_at = MAX_SLACK_MSG_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# A GFM table separator row, e.g. "|---|:---:|" — the signal that a chunk
# contains a markdown table and should go out as a native markdown block.
_MD_TABLE_SEP = re.compile(
    r"^ {0,3}\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)+\|?[ \t]*$",
    re.MULTILINE,
)


def post_response(channel: str, message: str, thread_ts: str | None = None) -> str | None:
    """Post a markdown response to Slack, chunked.

    Chunks containing a markdown table are sent as a native `markdown` block
    (Slack renders GFM tables, task lists, headers natively); everything else
    goes as plain mrkdwn text via md_to_slack. Returns the effective thread_ts
    (the first message's ts when not already in a thread).
    """
    parent_ts = thread_ts
    # Enforced on the raw text too: the native `markdown` block path below posts
    # `chunk` verbatim and never passes through md_to_slack.
    message = strip_link_emphasis(message)
    for chunk in chunk_message(message):
        fallback = md_to_slack(chunk)
        result = None
        if _MD_TABLE_SEP.search(chunk):
            try:
                result = slack_client.chat_postMessage(
                    channel=channel, thread_ts=parent_ts, text=fallback,
                    blocks=[{"type": "markdown", "text": chunk}],
                )
            except Exception as e:
                logger.warning(f"markdown block post failed, using plain text: {e}")
        if result is None:
            result = slack_client.chat_postMessage(
                channel=channel, thread_ts=parent_ts, text=fallback,
            )
        if parent_ts is None:
            parent_ts = result["ts"]
    return parent_ts


# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------


def download_slack_files(event: dict) -> list[Path]:
    """Download Slack file attachments to temp files for Claude to read."""
    files = event.get("files", [])
    if not files:
        return []

    downloaded = []
    for f in files:
        url = f.get("url_private_download") or f.get("url_private")
        if not url:
            continue

        name = f.get("name", "attachment")
        suffix = Path(name).suffix or ".bin"

        try:
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
            )
            with urllib.request.urlopen(req) as resp:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=suffix, prefix="slack-", delete=False
                )
                tmp.write(resp.read())
                tmp.close()
                downloaded.append(Path(tmp.name))
                logger.info(f"Downloaded Slack file: {name} -> {tmp.name}")
        except Exception as e:
            logger.error(f"Failed to download Slack file {name}: {e}")

    return downloaded


# File upload trigger: only paths prefixed with "attach:" are uploaded.
# Matches "attach:/path/to/file" or "attach:~/path/to/file" (with optional
# whitespace after the colon). This prevents accidental uploads when file
# paths are mentioned in normal conversation.
_ATTACH_PATTERN = re.compile(
    r'attach:\s*(~/[^\s`\'"<>|*?,]+\.\w+|/(?:Users|tmp|var|home)/[^\s`\'"<>|*?,]+\.\w+)',
    re.MULTILINE,
)


def _auto_upload_files(text: str, channel: str, thread_ts: str | None = None) -> None:
    """Scan text for attach:/path markers and upload matching files to Slack."""
    seen: set[str] = set()
    for match in _ATTACH_PATTERN.findall(text):
        fp_str = match.rstrip('.,;:!?)]`"\'')
        # Expand tilde to home directory
        if fp_str.startswith('~'):
            fp_str = str(Path.home() / fp_str[2:])
        if fp_str in seen:
            continue
        seen.add(fp_str)
        fp = Path(fp_str)
        if fp.exists() and fp.is_file():
            upload_file_to_slack(str(fp), channel, thread_ts=thread_ts)
            logger.info(f"Auto-uploaded file from response: {fp}")
        else:
            # An attach: marker whose file is missing must NOT fail silently —
            # otherwise the message text claims "attached" while nothing lands,
            # the recurring false-completion trap. Surface it loudly so the
            # sender (and the next turn) see the attachment didn't fire.
            logger.error(f"attach: marker points to a missing file, not uploaded: {fp}")
            try:
                slack_client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f":warning: Tried to attach `{fp}` but the file wasn't found — nothing uploaded.",
                )
            except Exception as e:
                logger.error(f"Failed to post missing-attachment notice for {fp}: {e}")


def upload_file_to_slack(
    file_path: str,
    channel: str,
    thread_ts: str | None = None,
    title: str | None = None,
    message: str | None = None,
) -> None:
    """
    Upload a file from the local machine to Slack.

    Uses Slack's v2 upload flow:
    1. Get a presigned upload URL
    2. POST the file to it
    3. Complete the upload (share to channel/thread)

    Claude can call this to share screenshots, CSVs, reports, etc.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return

    filename = title or path.name
    file_size = path.stat().st_size

    try:
        # Step 1: Get upload URL
        url_response = slack_client.files_getUploadURLExternal(
            filename=filename,
            length=file_size,
        )
        upload_url = url_response["upload_url"]
        file_id = url_response["file_id"]

        # Step 2: Upload the file
        with open(path, "rb") as f:
            import urllib.request as urlreq
            req = urlreq.Request(
                upload_url,
                data=f.read(),
                method="POST",
                headers={"Content-Type": "application/octet-stream"},
            )
            urlreq.urlopen(req)

        # Step 3: Complete the upload (share to channel)
        slack_client.files_completeUploadExternal(
            files=[{"id": file_id, "title": filename}],
            channel_id=channel,
            thread_ts=thread_ts,
            initial_comment=message or "",
        )

        logger.info(f"Uploaded file to Slack: {filename} ({file_size} bytes) -> {channel}")
    except Exception as e:
        logger.error(f"Failed to upload file {file_path}: {e}")
        # Fall back: post the file path so the user knows what happened
        slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"Tried to upload `{filename}` but failed: {e}",
        )


# ---------------------------------------------------------------------------
# Proactive messaging (CLI mode)
# ---------------------------------------------------------------------------


def _register_forward_via_server(dm_thread_ts: str, target_thread: str) -> bool:
    """Register a forward mapping via the running Flask server."""
    payload = json.dumps({
        "dm_thread_ts": dm_thread_ts,
        "target_thread": target_thread,
    }).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/internal/forward",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        logger.error(f"Failed to register forward: {e}")
        return False


def send_dm(
    user_id: str,
    message: str,
    session_id: str | None = None,
    thread_ts: str | None = None,
    forward_to: str | None = None,
) -> str | None:
    """Send a proactive DM. Returns thread_ts.

    If forward_to is set, registers a forward so the reply routes back
    to that thread's live session.
    """
    response = slack_client.conversations_open(users=[user_id])
    channel_id = response["channel"]["id"]

    effective_thread_ts = post_response(channel_id, message, thread_ts=thread_ts)

    # Auto-upload any file paths mentioned in the message
    _auto_upload_files(message, channel_id, thread_ts=effective_thread_ts)

    if session_id and effective_thread_ts:
        _save_session(effective_thread_ts, session_id)

    if forward_to and effective_thread_ts:
        ok = _register_forward_via_server(effective_thread_ts, forward_to)
        if ok:
            logger.info(f"Forward registered: DM {effective_thread_ts} → {forward_to}")
        else:
            logger.warning(f"Failed to register forward for DM {effective_thread_ts} → {forward_to}")

    audit_logger.info(
        f"PROACTIVE_DM | USER:{user_id} | CHANNEL:{channel_id} "
        f"| THREAD:{effective_thread_ts} | SESSION:{session_id or 'none'} "
        f"| FORWARD_TO:{forward_to or 'none'} | MSG_LEN:{len(message)}"
    )
    return effective_thread_ts


def send_to_channel(
    channel: str,
    message: str,
    session_id: str | None = None,
    thread_ts: str | None = None,
) -> str | None:
    """Post a message to a channel (optionally in a thread). Returns thread_ts."""
    effective_thread_ts = post_response(channel, message, thread_ts=thread_ts)

    # Auto-upload any file paths mentioned in the message
    _auto_upload_files(message, channel, thread_ts=effective_thread_ts)

    if session_id and effective_thread_ts:
        _save_session(effective_thread_ts, session_id)

    audit_logger.info(
        f"PROACTIVE_CHANNEL | CHANNEL:{channel} "
        f"| THREAD:{effective_thread_ts} | SESSION:{session_id or 'none'} "
        f"| MSG_LEN:{len(message)}"
    )
    return effective_thread_ts


# ---------------------------------------------------------------------------
# Async message processing (handles Slack's 3-second deadline)
#
# Slack requires HTTP 200 within 3 seconds. Claude takes minutes.
# So we respond immediately and process in a background thread.
# ---------------------------------------------------------------------------


def process_message_async(event: dict) -> None:
    """Process a message in a background thread.

    Uses long-lived Claude processes with stream-json I/O. If a process is
    already running for this thread, the message is piped to its stdin and
    queued automatically by the CLI. Otherwise a new process is spawned
    (resuming any prior session for the thread).
    """
    user_id = event.get("user", "")
    text = event.get("text", "").strip()
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts")
    msg_ts = event.get("ts")

    # --- Forward rewrite: if this reply is in a forwarded DM thread,
    # rewrite it to target the original thread instead (single-shot). ---
    is_forwarded = False
    reaction_channel = channel
    reaction_msg_ts = msg_ts
    forward = _get_forward(thread_ts)
    if forward:
        is_forwarded = True
        sender_name = _get_user_name(user_id)
        text = f"[{sender_name} ({user_id}) replied in DM thread {thread_ts}]:\n{text}"
        thread_ts = forward["thread"]
        channel = forward["channel"]
        user_id_for_session = forward["user_id"]
        _remove_forward(reaction_msg_ts if reaction_msg_ts != thread_ts else event.get("ts", ""))
        _remove_forward(event.get("thread_ts", ""))
        logger.info(f"Forward rewrite: DM reply → thread {thread_ts} in {channel}")
    else:
        user_id_for_session = user_id

    # Replace user mentions with readable names
    text = re.sub(
        r"<@([A-Z0-9]+)>",
        lambda m: f"@{_get_user_name(m.group(1))}",
        text,
    ).strip()

    # Download attachments
    attached_files = download_slack_files(event)

    if not text and not attached_files:
        return

    if attached_files:
        paths = ", ".join(str(fp) for fp in attached_files)
        label = "Files attached" if len(attached_files) > 1 else "File attached"
        text = f"{label}: {paths}" + (f"\n\n{text}" if text else "")

    # Forwarded messages already have attribution prepended; skip normal formatting
    if not is_forwarded:
        sender_name = _get_user_name(user_id)

        # For channel messages (not DMs), let Claude decide if it should respond.
        # These checks treat Claude and Codex sessions symmetrically so that
        # in-thread follow-ups on Codex channels don't get filtered out.
        has_existing_session = (
            _get_session(thread_ts) is not None
            or bot_codex._load_thread_id(thread_ts) is not None
        )

        # Check if there's already a live process for this thread (either harness)
        has_live_process = (
            (thread_ts in _live_sessions and _live_sessions[thread_ts].proc.poll() is None)
            or (thread_ts in _codex_sessions and _codex_sessions[thread_ts].proc.poll() is None)
        )

        # If this is a thread reply and we have no saved session AND no live process,
        # fetch the full thread history so Claude has context on what was said before.
        is_thread_reply = thread_ts != msg_ts
        thread_context = None
        if not has_existing_session and not has_live_process and is_thread_reply:
            thread_context = _fetch_thread_context(channel, thread_ts, msg_ts)

        is_public_channel = event.get("channel_type") == "channel"
        is_channel_message = event.get("channel_type") in ("channel", "group")
        if (
            is_public_channel
            and channel not in CODEX_CHANNEL_IDS
            and not _get_channel_name(channel).startswith(ALLOWED_CHANNEL_PREFIXES)
        ):
            logger.info(f"Ignoring message in non-allowed public channel {channel} ({_get_channel_name(channel)})")
            log_ignored_channel(event, "MESSAGE")
            return

        raw_text = event.get("text", "")
        mentions_claudie = (
            "claudie" in raw_text.lower()
            or (BOT_USER_ID and f"<@{BOT_USER_ID}>" in raw_text)
        )
        # The dedicated Codex channel is a direct conversation with Claudie,
        # so messages there do not need to repeat her name on every turn.
        directly_addressed = mentions_claudie or channel in CODEX_CHANNEL_IDS

        if is_channel_message and not has_existing_session and not has_live_process:
            # Pre-filter: only spawn a Claude process if the message actually
            # mentions Claudie by name or @tag.  This avoids wasting a full
            # process just to decide "SKIP" on channel noise.
            if not directly_addressed:
                logger.info(f"Pre-filtered message from {user_id} in {channel} (no mention)")
                return

        # Inject the SKIP-or-respond instruction whenever a channel message
        # isn't directly addressed to Claudie — including in-thread chatter
        # between teammates on a thread Claudie was once part of. Without
        # this, the model has no guidance to stay silent and tends to emit
        # "No response needed" prose that pollutes the channel.
        needs_skip_prompt = is_channel_message and not directly_addressed
        if needs_skip_prompt:
            channel_name = _get_channel_name(channel)
            prefix = (
                f"A new message in channel #{channel_name}. "
                "You are NOT directly addressed in this message. "
                "Respond with the single literal token \"SKIP\" — nothing else, no prose, no preamble. "
                "Do NOT say 'No response needed', 'Skipping this', 'Nothing for me to do here', "
                "'Staying out of this thread', or any variant. Those still get streamed to Slack as noise. "
                "Only break silence and respond with content if you're directly addressed by name "
                "or tagged in THIS specific message. Otherwise: emit \"SKIP\" and only \"SKIP\".\n\n"
            )
        else:
            prefix = ""

        if thread_context:
            text = prefix + f"{thread_context}\n\n[{sender_name}]({user_id}):\n{text}"
        else:
            text = prefix + f"[{sender_name}]({user_id}):\n{text}"

    # Add eyes reaction as thinking indicator (on the original message, not the rewritten one)
    try:
        slack_client.reactions_add(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
        logger.info(f"EYES_ADD ok channel={reaction_channel} ts={reaction_msg_ts}")
    except Exception as _e:
        logger.warning(f"EYES_ADD failed channel={reaction_channel} ts={reaction_msg_ts}: {_e}")

    # Get or create a live Claude process for this thread
    all_texts = []
    first_text_sent = False
    skip_detected = False

    # Soft-skip phrases — when the model writes one of these as its entire
    # first text block, treat it as SKIP. Catches "No response needed" and
    # similar variants the model emits when it means SKIP but doesn't follow
    # the exact-token instruction. Without this, the prose gets streamed to
    # Slack and pollutes the thread.
    SOFT_SKIP_PHRASES = (
        "no response needed",
        "nothing for me to do",
        "nothing for me here",
        "skipping this",
        "skipping that",
        "staying out of this thread",
        "staying out of it",
        "staying silent",
        "not addressed to me",
        "not for me",
        "not relevant to me",
        "i'll stay out",
        "i'll skip this",
        "no action needed from me",
    )

    def on_text(text_block: str):
        """Called for each text block Claude produces — post it to Slack immediately."""
        nonlocal first_text_sent, skip_detected

        # Check for SKIP on the very first text block (channel relevance filter)
        if not first_text_sent:
            stripped = text_block.strip()
            if stripped == "SKIP":
                skip_detected = True
                return
            # Soft-skip: short first block whose normalized text matches a
            # known skip phrase. Length cap avoids swallowing real responses
            # that happen to contain one of these substrings.
            normalized = stripped.lower().rstrip(".!? ")
            if len(stripped) <= 80 and normalized in SOFT_SKIP_PHRASES:
                logger.info(f"Soft-SKIP detected (suppressed prose): {stripped!r}")
                skip_detected = True
                return

        all_texts.append(text_block)

        # Content-free heartbeat blocks are recorded above (so the audit trail
        # still shows everything the model produced) but never posted. Gated on
        # first_text_sent: only INTERSTITIAL blocks are dropped, so a turn can
        # never go completely silent — the first block always ships.
        if first_text_sent and is_content_free_holding(text_block):
            logger.info(f"Holding filler suppressed (not posted): {text_block.strip()!r}")
            return

        # Auto-upload any file paths mentioned
        _auto_upload_files(text_block, channel, thread_ts=thread_ts)

        # Post to Slack (native markdown block when the chunk holds a table)
        post_response(channel, text_block, thread_ts=thread_ts)
        first_text_sent = True

    start = time.time()

    # Dispatch: Codex channels route through bot_codex; everything else
    # falls through to the unchanged Claude path below.
    if channel in CODEX_CHANNEL_IDS:
        try:
            codex_session = _get_or_create_codex_session(
                thread_ts=thread_ts, channel=channel, user_id=user_id_for_session,
                on_text=on_text, on_status=None,
            )
            bot_codex.send_to_codex(codex_session, text)
        except Exception as e:
            logger.error(f"Codex error in thread {thread_ts}: {e}")
            try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
            except Exception: pass
            slack_client.chat_postMessage(
                channel=channel, thread_ts=thread_ts,
                text=f":warning: Codex harness error: {e}",
            )
            return
        try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
        except Exception: pass
        duration = time.time() - start
        logger.info(f"Codex turn done in {duration:.1f}s for thread {thread_ts}")
        return

    try:
        session = _get_or_create_live_session(thread_ts, channel, user_id=user_id_for_session)

        # Real-time steering: a turn is already running in this thread — don't
        # hold the message until it finishes. Write it to stdin now; the CLI
        # delivers it at the next tool-call boundary inside the running turn,
        # exactly like typing without Esc in interactive Claude Code. The
        # running turn's on_text posts to this same thread, so replies route
        # correctly. If the turn ends in the race window the message simply
        # starts the next turn, and its eyes reaction is still drained by the
        # reader on that turn's result. `stop`/`esc` remains the hard
        # interrupt for aborting a slow tool call outright.
        if session.turn_lock.locked():
            _send_to_claude(session, text)
            session.pending_reactions.append((reaction_channel, reaction_msg_ts))
            audit_interaction(event, "(steered into running turn)", 0.0, session.session_id)
            logger.info(f"Steering message injected mid-turn in thread {thread_ts}")
            return

        # Acquire turn_lock — this serializes the send→wait cycle.
        # If another message is already being processed, we block here.
        with session.turn_lock:
            session._on_text = on_text
            session._turn_done.clear()

            _send_to_claude(session, text)

            if not session._turn_done.wait(timeout=CLAUDE_TIMEOUT):
                try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
                except Exception: pass
                minutes = CLAUDE_TIMEOUT // 60
                slack_client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text=f"Sorry, that timed out after {minutes} minutes. Try a simpler question?",
                )
                return

            # Check if the process died without producing a response
            if not all_texts and not skip_detected and session.proc.poll() is not None:
                try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
                except Exception: pass
                logger.error(f"Claude process died without responding in thread {thread_ts}")
                slack_client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text="Sorry, I lost my train of thought. Could you try sending that again?",
                )
                return

    except Exception as e:
        try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
        except Exception: pass
        logger.error(f"Error processing message in thread {thread_ts}: {e}")
        slack_client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"Something went wrong: {e}",
        )
        return

    duration = time.time() - start

    # If Claude decided not to respond (channel messages only), stay silent
    if skip_detected:
        try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
        except Exception: pass
        logger.info(f"Skipped message from {user_id} in {channel} (not relevant)")
        return

    # Remove eyes reaction
    try:
        slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
    except Exception:
        pass

    full_response = "\n\n".join(all_texts)
    audit_interaction(event, full_response, duration, session.session_id)


# ---------------------------------------------------------------------------
# In-thread stop (the Esc key for Slack)
# ---------------------------------------------------------------------------


def _interrupt_session(session: LiveSession) -> bool:
    """Send the CLI an interrupt (the programmatic Esc). True if the turn ended cleanly."""
    try:
        payload = json.dumps({"type": "control_request",
                              "request_id": f"interrupt-{int(time.time() * 1000)}",
                              "request": {"subtype": "interrupt"}})
        with session.stdin_lock:
            session.proc.stdin.write(payload + "\n")
            session.proc.stdin.flush()
    except Exception as e:
        logger.warning(f"Interrupt write failed for {session.thread_ts}: {e}")
    if session._turn_done.wait(timeout=5):
        return True
    # Interrupt didn't land — hard-kill; the thread resumes via --resume next message
    try:
        session.proc.terminate()
    except Exception:
        pass
    session._turn_done.set()
    return False


def _maybe_stop_from_message(event: dict) -> bool:
    """In-thread Esc: Slack blocks slash commands in thread reply boxes, so a
    bare 'stop' (or 'esc') in a thread with a running turn interrupts it
    instead of queueing as a normal message. Returns True if handled.

    Exact-match only — sentences containing 'stop' pass through untouched,
    and with no running turn the word falls through as a normal message.
    Authorized users only: interrupting a run is a control action, even in
    channels where unauthorized users may otherwise talk to the bot.
    """
    if not is_authorized(event.get("user", "")):
        return False
    text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip().lower()
    if text not in ("stop", "esc"):
        return False
    thread_ts = event.get("thread_ts") or event.get("ts")
    with _live_sessions_lock:
        session = _live_sessions.get(thread_ts)
    if not session or session.proc.poll() is not None or not session.turn_lock.locked():
        return False  # nothing running here — treat as a normal message

    def _do_stop():
        clean = _interrupt_session(session)
        note = ("stopped mid-run — tell me where to go instead" if clean
                else "had to hard-kill the process; the thread resumes with full context on your next message")
        try:
            slack_client.chat_postMessage(
                channel=session.channel, thread_ts=session.thread_ts,
                text=f"Stopped: {note}",
                blocks=[{"type": "context", "elements": [
                    {"type": "mrkdwn", "text": f":octagonal_sign: _{note}_"}]}],
            )
        except Exception:
            pass

    threading.Thread(target=_do_stop, daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Slack event handlers
# ---------------------------------------------------------------------------


@app.event("message")
def handle_message(event, say):
    """Handle DMs and channel messages."""
    subtype = event.get("subtype")
    if subtype and subtype != "file_share":
        return

    # Skip @mentions in channels — those are handled by handle_mention() via
    # the app_mention event.  Without this guard, Slack fires BOTH a "message"
    # event and an "app_mention" event for the same message, causing duplicate
    # responses.
    if BOT_USER_ID:
        text = event.get("text", "")
        if event.get("channel_type") != "im" and f"<@{BOT_USER_ID}>" in text:
            return

    # Check if this is a forwarded DM reply (auth bypass — the supervisor
    # who opened the DM implicitly authorized the reply)
    reply_thread = event.get("thread_ts") or event.get("ts")
    is_forwarded_reply = _get_forward(reply_thread) is not None

    user_id = event.get("user", "")
    if not is_forwarded_reply and not is_authorized(user_id):
        if event.get("channel_type") in ("im", "mpim"):
            log_unlisted_user(event, "REFUSED")
            say(text="I only respond to authorized users.", thread_ts=event.get("ts"))
            return
        # Falls through on purpose: a channel message from someone outside
        # AUTHORIZED_USERS still gets served. Logged as SERVED so the audit
        # trail stops calling answered messages rejections.
        log_unlisted_user(event, "SERVED")

    # In-thread Esc: bare "stop" while a turn is running interrupts it
    if _maybe_stop_from_message(event):
        return

    # Process async — return immediately so Slack gets its 200
    threading.Thread(target=process_message_async, args=(event,), daemon=True).start()


@app.event("app_mention")
def handle_mention(event, say):
    """Handle @bot mentions in channels."""
    user_id = event.get("user", "")
    channel = event.get("channel", "")

    is_public_channel = event.get("channel_type") == "channel"
    if (
        is_public_channel
        and channel not in CODEX_CHANNEL_IDS
        and not _get_channel_name(channel).startswith(ALLOWED_CHANNEL_PREFIXES)
    ):
        logger.info(f"Ignoring mention in non-allowed public channel {channel}")
        log_ignored_channel(event, "MENTION")
        return

    reply_thread = event.get("thread_ts") or event.get("ts")
    is_forwarded_reply = _get_forward(reply_thread) is not None

    if not is_forwarded_reply and not is_authorized(user_id):
        if event.get("channel_type") in ("im", "mpim"):
            log_unlisted_user(event, "REFUSED")
            say(text="I only respond to authorized users.", thread_ts=event.get("ts"))
            return
        # Falls through on purpose: a channel message from someone outside
        # AUTHORIZED_USERS still gets served. Logged as SERVED so the audit
        # trail stops calling answered messages rejections.
        log_unlisted_user(event, "SERVED")

    # "@bot stop" in a thread = in-thread Esc
    if _maybe_stop_from_message(event):
        return

    threading.Thread(target=process_message_async, args=(event,), daemon=True).start()


# Catch-all for events we subscribe to but don't handle
@app.event("member_joined_channel")
def handle_member_joined(event):
    pass


@app.event("reaction_added")
def handle_reaction(event):
    pass


@app.event("file_shared")
def handle_file_shared(event):
    pass


# ---------------------------------------------------------------------------
# Interactive actions (Block Kit buttons, menus, inputs)
#
# Requires Interactivity enabled in the Slack app config, Request URL pointed
# at the /slack/events endpoint (Bolt's SlackRequestHandler serves both events
# and interactive payloads). Clicks route back into the thread's session.
# ---------------------------------------------------------------------------


@app.action(re.compile(r".*"))
def handle_block_action(ack, body):
    """Route button clicks / menu selections into the thread's Claude session.

    Any interactive element the bot (or Claude via the SDK) posts lands here.
    The click becomes a structured message in the same thread, so Claude sees
    '[... clicked "Send it"]' and responds there. URL buttons are
    navigational — ack only.
    """
    ack()
    try:
        action = body["actions"][0]
        if action.get("url"):
            return

        user_id = body["user"]["id"]
        if not is_authorized(user_id):
            log_unlisted_user(body, "REFUSED")
            return

        atype = action.get("type", "")
        label = action.get("text", {}).get("text", "")
        value = action.get("value", "")
        if atype in ("static_select", "radio_buttons"):
            opt = action.get("selected_option") or {}
            label = opt.get("text", {}).get("text", label)
            value = opt.get("value", value)
        elif atype in ("checkboxes", "multi_static_select"):
            opts = action.get("selected_options") or []
            value = ", ".join(o.get("text", {}).get("text") or o.get("value", "") for o in opts)
            label = label or "selection"
        elif atype == "datepicker":
            value = action.get("selected_date") or ""
            label = label or "date"
        elif atype == "timepicker":
            value = action.get("selected_time") or ""
            label = label or "time"
        elif atype == "plain_text_input":
            label = label or "text input"
        desc = f'"{label}"' if label else f"action {action.get('action_id', '?')}"
        if value and value != label:
            desc += f" (value: {value})"

        message = body["message"]
        event = {
            "user": user_id,
            "channel": body["channel"]["id"],
            "ts": message["ts"],  # :eyes: lands on the clicked message
            "thread_ts": message.get("thread_ts") or message["ts"],
            # "Claudie" in the text keeps this from being SKIPped by the
            # channel-relevance filter when the click starts a fresh session
            "text": f"[Button click for Claudie: {_get_user_name(user_id)} clicked {desc} "
                    f"(action_id: {action.get('action_id', '')})]",
            # unique per click so repeat clicks on one message aren't deduped
            "client_msg_id": f"{action.get('action_id', '')}:{action.get('action_ts', '')}",
            "channel_type": body["channel"].get("name") == "directmessage" and "im" or "channel",
        }
        threading.Thread(target=process_message_async, args=(event,), daemon=True).start()
    except Exception as e:
        logger.error(f"Failed to route block action: {e}")


# ---------------------------------------------------------------------------
# Flask app (HTTP Events API)
# ---------------------------------------------------------------------------

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


# Interactive payloads (button clicks, menu picks). Slack can point the
# Interactivity Request URL here or at /slack/events — Bolt handles both.
@flask_app.route("/slack/actions", methods=["POST"])
def slack_actions():
    return handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "ai-employee"})


@flask_app.route("/internal/forward", methods=["POST"])
def internal_forward():
    """Register a forward mapping: DM thread → original thread. Localhost only."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "localhost only"}), 403

    data = request.get_json(force=True)
    dm_thread_ts = data.get("dm_thread_ts")
    target_thread = data.get("target_thread")
    if not dm_thread_ts or not target_thread:
        return jsonify({"error": "dm_thread_ts and target_thread required"}), 400

    with _live_sessions_lock:
        target_session = _live_sessions.get(target_thread)
        if not target_session or target_session.proc.poll() is not None:
            return jsonify({"error": f"no live session for thread {target_thread}"}), 404

        _add_forward(
            dm_thread_ts,
            target_thread=target_thread,
            target_channel=target_session.channel,
            session_id=target_session.session_id or "",
            user_id=target_session.user_id,
        )

    logger.info(f"Forward registered: {dm_thread_ts} → {target_thread}")
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="AI Employee — Slack Bot powered by Claude Code")
    parser.add_argument(
        "--send", nargs=2, metavar=("USER_ID", "MESSAGE"),
        help="Send a proactive DM and exit",
    )
    parser.add_argument(
        "--send-result", metavar="USER_ID",
        help="Read Claude JSON from stdin, send as DM with session linking",
    )
    parser.add_argument(
        "--thread", metavar="THREAD_TS",
        help="Reply in an existing thread (use with --send or --send-result)",
    )
    parser.add_argument(
        "--forward-to", metavar="THREAD_TS",
        help="Register a forward so the DM reply routes back to this thread",
    )
    parser.add_argument(
        "--session-id", metavar="SESSION_ID",
        help="Save this session ID for the new DM thread (for cron resume)",
    )
    parser.add_argument(
        "--channel", nargs=2, metavar=("CHANNEL", "MESSAGE"),
        help="Post a message to a channel and exit",
    )
    args = parser.parse_args()

    # CLI modes — send and exit
    if args.send:
        thread_ts = send_dm(
            args.send[0], args.send[1],
            session_id=args.session_id,
            thread_ts=args.thread,
            forward_to=args.forward_to,
        )
        if thread_ts:
            print(thread_ts)
        return

    if args.send_result:
        raw = sys.stdin.read().strip()
        try:
            data = json.loads(raw)
            message = data.get("result", "")
            session_id = data.get("session_id")
        except json.JSONDecodeError:
            message = raw
            session_id = None
        if not message:
            message = "Job completed but produced no output."
        send_dm(args.send_result, message, session_id=session_id, thread_ts=args.thread)
        return

    if args.channel:
        send_to_channel(
            args.channel[0], args.channel[1],
            session_id=args.session_id, thread_ts=args.thread,
        )
        return

    # Server mode
    if not SLACK_BOT_TOKEN or not SLACK_SIGNING_SECRET:
        logger.error("Missing SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET in .env")
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    logger.info(f"{BOT_DISPLAY_NAME} starting on port {PORT}")
    logger.info(f"Authorized users: {AUTHORIZED_USERS or 'all'}")
    logger.info(f"Project dir: {PROJECT_DIR}")

    # GC expired forward entries on startup
    _gc_forwards()

    # Start idle session cleanup thread
    threading.Thread(target=_cleanup_idle_sessions, daemon=True).start()

    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
