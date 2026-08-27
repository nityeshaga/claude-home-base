#!/usr/bin/env python3
"""
Your AI Employee — Slack bot powered by Claude Code.

HTTP Events API version (production-standard). Uses Flask + Cloudflare Tunnel
instead of Socket Mode. Slack sends stateless HTTP POSTs to your public URL.

Key difference from Socket Mode: Slack requires a 200 response within 3 seconds.
Claude Code calls take minutes, so we respond immediately and process in a
background thread, posting the result when ready.

Also supports proactive messaging and read access via CLI:
    python bot.py --send USER_ID "message"
    python bot.py --channel "#general" "message"
    echo '{"result":"..."}' | python bot.py --send-result USER_ID
    python bot.py --history CHANNEL_ID [--limit 50] [--thread THREAD_TS]
    python bot.py --find-channel SUBSTRING
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
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient

import bot_codex  # alternate backend: rooms with "backend": "codex" route here

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
PROJECT_DIR = os.environ.get("PROJECT_DIR", "")
if not PROJECT_DIR:
    logger.error("PROJECT_DIR not set. Add it to .env")
    raise SystemExit(1)

CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "7200"))  # 2 hour default

# Supervisor users get --dangerously-skip-permissions; everyone else gets --permission-mode dontAsk
SUPERVISOR_USERS = set(
    u.strip() for u in os.environ.get("SUPERVISOR_USERS", "").split(",") if u.strip()
) or AUTHORIZED_USERS  # default: all authorized users are supervisors

# Restricted users get limited tool access (--allowedTools / --disallowedTools).
# Non-supervisors who aren't in RESTRICTED_USERS get plain dontAsk with no tool filtering.
RESTRICTED_USERS = set(
    u.strip() for u in os.environ.get("RESTRICTED_USERS", "").split(",") if u.strip()
)
RESTRICTED_ALLOWED_TOOLS = [
    t.strip() for t in os.environ.get(
        "RESTRICTED_ALLOWED_TOOLS",
        "Read,Edit,Write,Grep,Glob,Bash,WebSearch,WebFetch,Agent"
    ).split(",") if t.strip()
]
RESTRICTED_DISALLOWED_TOOLS = [
    t.strip() for t in os.environ.get("RESTRICTED_DISALLOWED_TOOLS", "").split(",") if t.strip()
]

# Channel filtering — only respond in channels whose names contain one of these substrings.
# Applies to both public and private channels. DMs/MPIMs are unaffected — those are
# governed by AUTHORIZED_USERS. Leave empty to respond in all channels.
ALLOWED_CHANNEL_SUBSTRINGS = tuple(
    p.strip().lower() for p in os.environ.get("ALLOWED_CHANNELS", "").split(",") if p.strip()
)

# Trust battery — optional. Set to a directory containing per-user JSON battery files.
TRUST_BATTERY_DIR = os.environ.get("TRUST_BATTERY_DIR", "")

MAX_SLACK_MSG_LEN = 3900
PORT = int(os.environ.get("PORT", "3000"))

# Per-channel/DM model + effort and per-model prompts live in model-config.json
# next to this script (start from model-config.json.example; the file explorer's
# /models page is a friendly editor). Read fresh on every claude spawn — no bot
# restart needed. No entry for a room → the config's own "default_model"; no
# default_model either → the CLI default from ~/.claude/settings.json.
MODEL_CONFIG_FILE = Path(__file__).resolve().parent / "model-config.json"
DEFAULT_EFFORT = "medium"
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def _load_model_config() -> dict:
    try:
        return json.loads(MODEL_CONFIG_FILE.read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:  # corrupt JSON must not take the bot down
        logger.warning(f"model-config.json unreadable ({e}); using CLI defaults")
        return {}


def _settings_default_model() -> str:
    """The model claude falls back to when --model is absent (~/.claude/settings.json)."""
    try:
        return json.loads((Path.home() / ".claude" / "settings.json").read_text()).get("model", "") or ""
    except Exception:
        return ""


def _resolve_entry(channel_id: str, user_id: str) -> dict:
    """The merged model-config entry for a room: channel entry, with a DM
    per-user entry layered on top (its non-empty keys win)."""
    cfg = _load_model_config()
    entry = dict(cfg.get("channels", {}).get(channel_id, {}))
    if channel_id.startswith("D"):
        entry.update({k: v for k, v in cfg.get("dm_users", {}).get(user_id, {}).items() if v})
    return entry


# Models that route through the Codex backend rather than the Claude CLI. A room
# whose selected model matches routes to bot_codex — so picking one on the
# /models page is all it takes to make a channel Codex-backed. An explicit
# "backend" key in the config entry still wins (see resolve_backend).
_CODEX_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4", "codex")


def _is_codex_model(model: str) -> bool:
    return bool(model) and model.lower().startswith(_CODEX_MODEL_PREFIXES)


def _effective_model(cfg: dict, entry: dict) -> str:
    """The model a room actually gets: its own, else the config's default_model,
    else "" — meaning the CLI default from ~/.claude/settings.json."""
    return entry.get("model") or cfg.get("default_model") or ""


def resolve_backend(channel_id: str, user_id: str) -> str:
    """Which engine drives this room — "claude" (default) or "codex".

    An explicit `"backend"` in the room's model-config entry wins; otherwise the
    engine is inferred from the model in play (a gpt-*/o* model → codex). That
    way the single model dropdown on the /models page switches engines too, with
    no second control to keep in sync.
    """
    cfg = _load_model_config()
    entry = _resolve_entry(channel_id, user_id)
    explicit = entry.get("backend")
    if explicit:
        return explicit.lower()
    return "codex" if _is_codex_model(_effective_model(cfg, entry)) else "claude"


def resolve_model_settings(channel_id: str, user_id: str) -> tuple[str, str, str]:
    """(model or "" for CLI default, effort, per-model prompt or "").

    DM per-user override beats the channel entry, which beats the config's own
    default_model; effort falls back to default_effort. The prompt is keyed by the
    model actually in play — including the settings.json default when nothing is
    set anywhere — so a per-model prompt follows the model everywhere.
    """
    cfg = _load_model_config()
    entry = _resolve_entry(channel_id, user_id)
    model = _effective_model(cfg, entry)
    effort = entry.get("effort") or cfg.get("default_effort") or DEFAULT_EFFORT
    if effort not in _EFFORTS:
        logger.warning(f"bad effort {effort!r} for {channel_id}; using {DEFAULT_EFFORT}")
        effort = DEFAULT_EFFORT
    prompt = (cfg.get("model_prompts", {}).get(model or _settings_default_model()) or "").strip()
    return model, effort, prompt


def resolve_prompt_cadence(channel_id: str, user_id: str) -> tuple[int, str]:
    """(every-N-messages, per-model prompt) for re-injecting the prompt mid-session.

    The prompt always goes in the system prompt at spawn; a cadence of N > 0 also
    appends it to every Nth message the human sends, so a standing instruction
    survives a long thread instead of decaying. 0 (the default) = spawn only.
    """
    cfg = _load_model_config()
    entry = _resolve_entry(channel_id, user_id)
    model = _effective_model(cfg, entry) or _settings_default_model()
    prompt = (cfg.get("model_prompts", {}).get(model) or "").strip()
    try:
        every = int(cfg.get("model_prompt_cadence", {}).get(model) or 0)
    except (TypeError, ValueError):
        every = 0
    return max(every, 0), prompt

VOTES_FILE = Path(__file__).parent / "votes.json"

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


_channel_private_cache: dict[str, bool] = {}


def _is_channel_private(channel_id: str) -> bool:
    """Check whether a Slack channel is private, with caching.

    Modern Slack reports `channel_type: "channel"` in events for both public
    and private channels — the only reliable signal is the `is_private` flag
    on the channel object.
    """
    if channel_id in _channel_private_cache:
        return _channel_private_cache[channel_id]
    try:
        info = slack_client.conversations_info(channel=channel_id)
        priv = bool(info["channel"].get("is_private", False))
    except Exception:
        priv = False
    _channel_private_cache[channel_id] = priv
    return priv


def _channel_allowed(channel_id: str, channel_type: str) -> bool:
    """True if Andy should respond in this channel.

    - DMs (im) and group DMs (mpim): always pass; gated by AUTHORIZED_USERS elsewhere.
    - Private channels: always pass — Slack only delivers events for channels
      Andy's a member of, so receiving an event implies she's been explicitly
      invited. Membership = consent to participate. Note: modern private
      channels report `channel_type: "channel"` (not "group"), so we check
      `is_private` via the channel object.
    - Public channels: must contain at least one of ALLOWED_CHANNEL_SUBSTRINGS
      in the name (case-insensitive). Empty list = all pass.
    """
    if channel_type in ("im", "mpim", "group"):
        return True
    if _is_channel_private(channel_id):
        return True
    if not ALLOWED_CHANNEL_SUBSTRINGS:
        return True
    name = _get_channel_name(channel_id).lower()
    return any(sub in name for sub in ALLOWED_CHANNEL_SUBSTRINGS)


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
# Cross-thread forward map: when Claude DMs someone in a side thread to ask a
# question, register a forward so that any reply in that side thread routes
# back into the original conversation thread instead of starting a new one.
# Single-shot — the entry is removed once the first reply has been forwarded.
# ---------------------------------------------------------------------------

FORWARDS_FILE = LOG_DIR / ".forwards.json"
FORWARDS_MAX_AGE_SECONDS = 14 * 24 * 3600
_forwards_lock = threading.Lock()


def _load_forwards() -> dict:
    try:
        return json.loads(FORWARDS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_forwards(fwds: dict) -> None:
    FORWARDS_FILE.write_text(json.dumps(fwds))


def _add_forward(
    from_thread: str,
    to_thread: str,
    to_channel: str,
    session_id: str | None,
    user_id: str,
) -> None:
    with _forwards_lock:
        fwds = _load_forwards()
        fwds[from_thread] = {
            "thread": to_thread,
            "channel": to_channel,
            "session_id": session_id,
            "user_id": user_id,
            "registered_at": time.time(),
        }
        _write_forwards(fwds)


def _get_forward(from_thread: str) -> dict | None:
    return _load_forwards().get(from_thread)


def _remove_forward(from_thread: str) -> None:
    with _forwards_lock:
        fwds = _load_forwards()
        if fwds.pop(from_thread, None) is not None:
            _write_forwards(fwds)


def _gc_forwards() -> None:
    cutoff = time.time() - FORWARDS_MAX_AGE_SECONDS
    with _forwards_lock:
        fwds = _load_forwards()
        stale = [k for k, v in fwds.items() if v.get("registered_at", 0) < cutoff]
        if not stale:
            return
        for k in stale:
            del fwds[k]
        _write_forwards(fwds)
        logger.info(f"Garbage-collected {len(stale)} stale forward entries")


# ---------------------------------------------------------------------------
# Live session management: long-lived Claude processes with stream-json I/O
#
# Instead of spawning a new `claude -p` subprocess for every message (which
# causes race conditions when multiple messages arrive for the same thread),
# we keep Claude processes alive and pipe messages to their stdin as JSON.
# The CLI queues them automatically, matching terminal behavior.
# ---------------------------------------------------------------------------

IDLE_TIMEOUT = 10800  # 3 hours — kill process if no messages
MAX_LIVE_SESSIONS = 5  # max concurrent Claude processes (memory guard)


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
    # Model last announced in the thread (from message.model on assistant
    # events — the served model, not the --model flag). "" = not yet announced.
    model_notified: str = ""
    # Messages sent into this process, for the per-model prompt cadence. Resets
    # when the thread's process is respawned after an idle-out.
    turns_sent: int = 0


# thread_ts → LiveSession
_live_sessions: dict[str, LiveSession] = {}
_live_sessions_lock = threading.Lock()

# thread_ts → count of inbound messages seen in multi-person spaces (public
# channels + group DMs). Used to re-inject the relevance reminder every
# REMINDER_EVERY messages, since Claude drifts back to over-responding once a
# thread gets long. Guarded by _live_sessions_lock. Not GC'd — grows slowly.
_thread_msg_counts: dict[str, int] = {}
REMINDER_EVERY = 10

# Usage-limit pause: when the account is out of usage, the Claude CLI itself
# synthesizes an assistant message like "You've hit your limit · resets 4pm
# (UTC)" — the model never runs, so the SKIP relevance filter can't suppress
# it. We intercept that text before it reaches Slack, announce the outage
# once, and stop forwarding inbound messages until the reset time. Limits are
# account-wide, so the pause is a single global, not per-thread.
LIMIT_RE = re.compile(r"You've hit your (usage )?limit", re.I)
LIMIT_RESET_RE = re.compile(r"resets\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
LIMIT_PAUSE_FALLBACK = 1800  # seconds, if the reset time can't be parsed
_limit_pause_lock = threading.Lock()
_limit_pause = {"until": 0.0, "announced": False}


def _parse_limit_reset(text: str) -> float:
    """Parse 'resets 4pm (UTC)' into an epoch timestamp (next occurrence)."""
    m = LIMIT_RESET_RE.search(text)
    if not m:
        return time.time() + LIMIT_PAUSE_FALLBACK
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "pm":
        hour += 12
    minute = int(m.group(2) or 0)
    now = datetime.now(timezone.utc)
    reset = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if reset <= now:
        reset += timedelta(days=1)
    # Small buffer so we don't resume a minute before the limit actually lifts
    return reset.timestamp() + 120


def _limit_paused() -> bool:
    """True while the usage-limit pause is active. Self-resets on expiry."""
    with _limit_pause_lock:
        if _limit_pause["until"] and time.time() >= _limit_pause["until"]:
            _limit_pause["until"] = 0.0
            _limit_pause["announced"] = False
        return _limit_pause["until"] > 0.0


def _enter_limit_pause(text: str) -> float | None:
    """Record a usage-limit notice. Returns the pause-end epoch if this call
    is the one that should announce the outage in Slack, else None."""
    with _limit_pause_lock:
        _limit_pause["until"] = max(_limit_pause["until"], _parse_limit_reset(text))
        if _limit_pause["announced"]:
            return None
        _limit_pause["announced"] = True
        return _limit_pause["until"]


def _get_trust_battery_context() -> str:
    """Read trust battery JSON files and format a context summary for Claude.

    Returns an empty string if trust batteries are not configured or no files exist.
    """
    if not TRUST_BATTERY_DIR:
        return ""
    battery_dir = Path(TRUST_BATTERY_DIR)
    if not battery_dir.exists():
        return ""
    tiers = [
        (0, 25, "Propose and Wait"),
        (25, 50, "Routine Execution"),
        (50, 75, "Judgment Calls"),
        (75, 100, "Full Autonomy"),
    ]
    lines = ["## Trust Battery — Current State"]
    for fpath in sorted(battery_dir.glob("*.json")):
        try:
            data = json.loads(fpath.read_text())
            name = data.get("team_member", fpath.stem)
            charge = data.get("current_charge", 0)
            last_updated = data.get("last_updated", "unknown")
            last_delta = 0.0
            if data.get("history"):
                last_delta = data["history"][-1].get("delta", 0.0)
            tier = next((t for lo, hi, t in tiers if lo <= charge < hi), "Full Autonomy")
            sign = "+" if last_delta >= 0 else ""
            lines.append(f"- {name}: {charge:.1f}% ({tier}) | Last: {sign}{last_delta:.1f} on {last_updated}")
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


def _spawn_claude_process(
    session_id: str | None = None,
    user_id: str = "",
    thread_ts: str = "",
    channel: str = "",
) -> subprocess.Popen:
    """Spawn a long-lived Claude CLI process with stream-json I/O.

    Injects CLAUDE_THREAD_TS / CLAUDE_CHANNEL_ID / CLAUDE_SESSION_ID env vars
    so the spawned Claude can read its own routing context (mainly for the
    cross-thread DM pattern — passing `--forward-to $CLAUDE_THREAD_TS`).
    """
    battery_context = _get_trust_battery_context()
    model, effort, model_prompt = resolve_model_settings(channel, user_id)
    cmd = [
        "claude",
        "-p", battery_context,
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--effort", effort,
    ]
    if model:
        cmd.extend(["--model", model])
    if model_prompt:
        cmd.extend(["--append-system-prompt", model_prompt])
    if user_id in SUPERVISOR_USERS:
        cmd.extend(["--permission-mode", "bypassPermissions"])
    elif user_id in RESTRICTED_USERS:
        cmd.extend(["--permission-mode", "dontAsk"])
        if RESTRICTED_ALLOWED_TOOLS:
            cmd.extend(["--allowedTools", " ".join(RESTRICTED_ALLOWED_TOOLS)])
        if RESTRICTED_DISALLOWED_TOOLS:
            cmd.extend(["--disallowedTools", " ".join(RESTRICTED_DISALLOWED_TOOLS)])
    else:
        cmd.extend(["--permission-mode", "dontAsk"])
    if session_id:
        cmd.extend(["--resume", session_id])

    stderr_tmp = tempfile.NamedTemporaryFile(
        mode="w+", suffix=".stderr", delete=False
    )

    proc_env = {**os.environ}
    if thread_ts:
        proc_env["CLAUDE_THREAD_TS"] = thread_ts
    if channel:
        proc_env["CLAUDE_CHANNEL_ID"] = channel
    if session_id:
        proc_env["CLAUDE_SESSION_ID"] = session_id

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_tmp,
        text=True,
        cwd=PROJECT_DIR,
        env=proc_env,
    )
    perm_mode = "bypassPermissions" if user_id in SUPERVISOR_USERS else "dontAsk"
    logger.info(f"Spawned Claude process pid={proc.pid} (resume={session_id or 'none'}, user={user_id}, permissions={perm_mode})")
    return proc


# Announce context utilization in the thread every N tokens (bot-side only —
# the notice never enters Claude's context)
CTX_NOTIFY_STEP = 100_000
CTX_WINDOW = 1_000_000


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


def _post_model_notice(session: LiveSession, model: str, prev: str) -> None:
    """Post a small grey context-block notice naming the serving model.

    `model` comes from message.model on the assistant event — the API's report
    of which model actually produced the response, so it stays truthful under
    silent fallbacks (e.g. opus-5 → opus-4-8). Posted once per session and
    again only if the served model ever changes.
    """
    try:
        note = f"model: {model}" if not prev else f"model changed: {prev} → {model}"
        slack_client.chat_postMessage(
            channel=session.channel, thread_ts=session.thread_ts,
            text=note,
            blocks=[{"type": "context", "elements": [
                {"type": "mrkdwn", "text": f":robot_face: _{note}_"}]}],
        )
    except Exception as e:
        logger.warning(f"Failed to post model notice: {e}")


def _track_model(session: LiveSession, data: dict) -> None:
    """Announce the served model on the first main-loop assistant event of a
    session, and re-announce if it changes mid-thread (fallback routing).
    Subagent events are skipped — they may run a different model than the
    thread itself."""
    if data.get("parent_tool_use_id"):
        return
    model = data.get("message", {}).get("model") or ""
    if model and model != session.model_notified:
        _post_model_notice(session, model, session.model_notified)
        session.model_notified = model


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
                _track_model(session, data)
                _track_context(session, data)
                content = data.get("message", {}).get("content", [])
                # Subagent (Agent/Task) events stream through the same stdout
                # with parent_tool_use_id set — their text is internal chatter,
                # not a reply to the human. Only main-loop text reaches Slack.
                if data.get("parent_tool_use_id"):
                    continue
                for block in content:
                    # Skill visibility: announce main-loop skill invocations in a
                    # grey context block (bot-side only, never enters Claude's
                    # context).
                    if (isinstance(block, dict) and block.get("type") == "tool_use"
                            and block.get("name") == "Skill"):
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

        # Evict oldest idle session if at capacity
        if len(_live_sessions) >= MAX_LIVE_SESSIONS:
            oldest_ts = min(_live_sessions, key=lambda k: _live_sessions[k].last_activity)
            oldest = _live_sessions.pop(oldest_ts)
            logger.info(f"Evicting idle session for thread {oldest_ts} (pid={oldest.proc.pid})")
            try:
                oldest.proc.stdin.close()
                oldest.proc.wait(timeout=10)
            except Exception:
                oldest.proc.kill()

        saved_session_id = _get_session(thread_ts)
        proc = _spawn_claude_process(
            session_id=saved_session_id,
            user_id=user_id,
            thread_ts=thread_ts,
            channel=channel,
        )
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


# Parallel registry for Codex-backed sessions (rooms with "backend": "codex").
# Kept separate from _live_sessions so the Claude path is untouched; both are
# consulted symmetrically when deciding whether a thread already has a session.
_codex_sessions: dict[str, "bot_codex.CodexSession"] = {}
_codex_sessions_lock = threading.Lock()


def _get_or_create_codex_session(thread_ts: str, channel: str, user_id: str,
                                 on_text, on_status=None) -> "bot_codex.CodexSession":
    """Get an existing Codex session for this Slack thread or spawn a fresh one.

    Mirrors _get_or_create_live_session but routes through bot_codex. The room's
    Codex model comes from model-config.json (resolve_model_settings)."""
    with _codex_sessions_lock:
        existing = _codex_sessions.get(thread_ts)
        if existing and existing.proc.poll() is None:
            existing.last_activity = time.time()
            existing._on_text = on_text
            existing._on_status = on_status
            return existing

        model, _effort, _prompt = resolve_model_settings(channel, user_id)
        session = bot_codex.spawn_codex_session(
            thread_ts=thread_ts, channel=channel, user_id=user_id,
            on_text=on_text, on_status=on_status, model=model or None,
        )
        _codex_sessions[thread_ts] = session
        return session


def _send_to_claude(session: LiveSession, text: str) -> None:
    """Send a user message to a live Claude process via stdin."""
    session.turns_sent += 1
    every, model_prompt = resolve_prompt_cadence(session.channel, session.user_id)
    if model_prompt and every and session.turns_sent % every == 0:
        text += f"\n\n[reminder]\n{model_prompt}"
        logger.info(f"Re-injected model prompt at message {session.turns_sent} "
                    f"in thread {session.thread_ts}")
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


def log_unauthorized(event: dict) -> None:
    user = event.get("user", "unknown")
    channel = event.get("channel", "unknown")
    text = event.get("text", "")[:100]
    audit_logger.warning(
        f'UNAUTHORIZED | USER:{user} | CHANNEL:{channel} | MSG:"{text}"'
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


def audit_skipped(event: dict, duration: float, session_id: str | None) -> None:
    """Record a turn the model deliberately did not answer.

    Answering a channel message with the literal token SKIP is correct
    behaviour — the room was not talking to us. But the skip path used to
    `return` before any audit write, so the ENTIRE inbound message left zero
    trace in audit.log. bot.log kept the sender and the channel and threw the
    text away.

    That is not a cosmetic gap. On 2026-08-26 a supervisor answered a live
    escalation in-thread and named an owner for the fix. She had addressed a
    teammate rather than the bot, so SKIP was right and the text was dropped.
    Ninety minutes later another session in that same channel announced the
    question was "still unruled" — because nothing it could read said
    otherwise. The decision had been made, received, and erased, and the
    person on the lowest charge on the board learned that her input does not
    register.

    SKIP suppresses the POST. It must never suppress the RECORD.

    SKIPPED:SUPERVISOR is broken out on purpose: a dropped supervisor message
    is the case most likely to have been a decision, and it is the one worth
    finding in a grep. Truncation matches audit_interaction (200 chars) so a
    ruling survives at readable length.
    """
    user = event.get("user", "unknown")
    if isinstance(user, dict):                    # button clicks nest the id
        user = user.get("id", "unknown")
    label = "SKIPPED:SUPERVISOR" if user in SUPERVISOR_USERS else "SKIPPED"
    channel = event.get("channel", "unknown")
    text = event.get("text", "")[:200]
    audit_logger.info(
        f"{label} | USER:{user} | CHANNEL:{channel} "
        f"| SESSION:{session_id or 'new'} | DURATION:{duration:.1f}s "
        f'| MSG:"{text}"'
    )


# ---------------------------------------------------------------------------
# Claude CLI (uses long-lived processes with stream-json I/O — see above)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Markdown → Slack mrkdwn
# ---------------------------------------------------------------------------


def md_to_slack(text: str) -> str:
    """Convert GitHub-flavored markdown to Slack mrkdwn."""
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
# Voting (Block Kit interactive buttons)
# ---------------------------------------------------------------------------

_votes_lock = threading.Lock()


def _load_votes() -> dict:
    if VOTES_FILE.exists():
        try:
            return json.loads(VOTES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_votes(votes: dict) -> None:
    VOTES_FILE.write_text(json.dumps(votes, indent=2))


def _vote_key(channel: str, ts: str) -> str:
    return f"{channel}:{ts}"


def _build_vote_blocks(text: str, vote_key: str, votes: dict | None = None) -> list[dict]:
    """Build Block Kit blocks: message text + voting buttons with current tallies."""
    entry = (votes or {}).get(vote_key, {})
    strong_users = entry.get("strong", [])
    pass_users = entry.get("pass", [])

    strong_names = [_get_user_name(u) for u in strong_users]
    pass_names = [_get_user_name(u) for u in pass_users]

    strong_label = f":+1: strong ({len(strong_users)})" if strong_users else ":+1: strong"
    pass_label = f":-1: pass ({len(pass_users)})" if pass_users else ":-1: pass"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "block_id": f"votes_{vote_key}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": strong_label, "emoji": True},
                    "action_id": "vote_strong",
                    "value": vote_key,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": pass_label, "emoji": True},
                    "action_id": "vote_pass",
                    "value": vote_key,
                },
            ],
        },
    ]

    if strong_names or pass_names:
        parts = []
        if strong_names:
            parts.append(f":+1: {', '.join(strong_names)}")
        if pass_names:
            parts.append(f":-1: {', '.join(pass_names)}")
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "  ·  ".join(parts)}],
        })

    return blocks


def _handle_vote(action_id: str, vote_key: str, user_id: str) -> None:
    """Record a vote and update the Slack message."""
    vote_type = "strong" if action_id == "vote_strong" else "pass"
    other_type = "pass" if vote_type == "strong" else "strong"

    with _votes_lock:
        votes = _load_votes()
        entry = votes.setdefault(vote_key, {"strong": [], "pass": [], "text": "", "channel": ""})

        if user_id in entry.get(vote_type, []):
            entry[vote_type].remove(user_id)
        else:
            if user_id in entry.get(other_type, []):
                entry[other_type].remove(user_id)
            entry.setdefault(vote_type, []).append(user_id)

        _save_votes(votes)

    channel, ts = vote_key.split(":", 1)
    text = entry.get("text", "")
    blocks = _build_vote_blocks(text, vote_key, votes)

    try:
        slack_client.chat_update(
            channel=channel,
            ts=ts,
            blocks=blocks,
            text=text,
        )
    except Exception as e:
        logger.error(f"Failed to update vote message: {e}")


def post_with_votes(channel: str, text: str, thread_ts: str | None = None) -> str | None:
    """Post a message with voting buttons. Returns the message ts."""
    slack_text = md_to_slack(text)
    placeholder_key = "pending"
    blocks = _build_vote_blocks(slack_text, placeholder_key)

    result = slack_client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text=slack_text,
        thread_ts=thread_ts,
    )
    ts = result["ts"]

    vote_key = _vote_key(channel, ts)
    blocks = _build_vote_blocks(slack_text, vote_key)
    slack_client.chat_update(channel=channel, ts=ts, blocks=blocks, text=slack_text)

    with _votes_lock:
        votes = _load_votes()
        votes[vote_key] = {"strong": [], "pass": [], "text": slack_text, "channel": channel}
        _save_votes(votes)

    return ts


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


def send_dm(
    user_id: str,
    message: str,
    session_id: str | None = None,
    thread_ts: str | None = None,
    forward_to: str | None = None,
) -> str | None:
    """Send a proactive DM. Returns thread_ts.

    If `forward_to` is set, registers a cross-thread forward: any reply in
    this new DM thread will be routed into the live session for `forward_to`
    instead of starting a new conversation here. Requires the running bot
    server to have a live session for `forward_to`.
    """
    response = slack_client.conversations_open(users=[user_id])
    channel_id = response["channel"]["id"]

    effective_thread_ts = post_response(channel_id, message, thread_ts=thread_ts)

    # Auto-upload any file paths mentioned in the message
    _auto_upload_files(message, channel_id, thread_ts=effective_thread_ts)

    if session_id and effective_thread_ts:
        _save_session(effective_thread_ts, session_id)

    if forward_to and effective_thread_ts:
        _register_forward_via_server(effective_thread_ts, forward_to)

    audit_logger.info(
        f"PROACTIVE_DM | USER:{user_id} | CHANNEL:{channel_id} "
        f"| THREAD:{effective_thread_ts} | SESSION:{session_id or 'none'} "
        f"| FORWARD_TO:{forward_to or 'none'} | MSG_LEN:{len(message)}"
    )
    return effective_thread_ts


def _register_forward_via_server(from_thread: str, to_thread: str) -> None:
    """Call the running bot server to register a forward.

    The server has the in-memory live-session map and can resolve channel,
    session_id, and user_id for the target thread. This CLI invocation can't.
    """
    url = f"http://127.0.0.1:{PORT}/internal/forward"
    payload = json.dumps({"from_thread": from_thread, "to_thread": to_thread}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                body = resp.read().decode(errors="replace")
                logger.error(f"Forward registration failed: {resp.status} {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        logger.error(f"Forward registration failed: {e.code} {body}")
        raise
    except Exception as e:
        logger.error(f"Forward registration error: {e}")
        raise


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
# Read access (CLI mode) — read messages from any channel Andy has scope for
# ---------------------------------------------------------------------------


def fetch_channel_history(
    channel: str,
    limit: int = 50,
    thread_ts: str | None = None,
) -> str:
    """Return formatted message history for a channel, or a single thread.

    Works for any channel type Andy's token has scope for. Private channels
    require Andy to be a member. Public channels do not — `channels:history`
    scope is sufficient. If she gets `not_in_channel`, she can self-join via
    `slack_client.conversations_join(channel=...)` for public channels.
    """
    if thread_ts:
        result = slack_client.conversations_replies(
            channel=channel, ts=thread_ts, limit=limit,
        )
    else:
        result = slack_client.conversations_history(channel=channel, limit=limit)
    msgs = result.get("messages", [])
    if not msgs:
        return "(no messages)"
    if not thread_ts:
        msgs = list(reversed(msgs))  # history returns newest-first; flip to chronological
    lines = []
    for m in msgs:
        ts = m.get("ts", "")
        u = m.get("user", "") or m.get("bot_id", "")
        name = _get_user_name(m["user"]) if m.get("user") else (m.get("username") or m.get("bot_id") or "(system)")
        text = (m.get("text") or "").strip()
        lines.append(f"[{ts}] {name} ({u}): {text}")
    return "\n".join(lines)


def find_channel(query: str, limit: int = 25) -> str:
    """List public + private channels whose name contains `query` (case-insensitive)."""
    q = query.lower()
    out = []
    cursor = None
    while True:
        resp = slack_client.conversations_list(
            types="public_channel,private_channel",
            limit=200,
            cursor=cursor,
            exclude_archived=True,
        )
        for c in resp.get("channels", []):
            name = c.get("name", "")
            if q in name.lower():
                kind = "private" if c.get("is_private") else "public"
                member = " [member]" if c.get("is_member") else ""
                out.append(f"{c['id']}\t#{name}\t{kind}{member}")
                if len(out) >= limit:
                    return "\n".join(out)
        cursor = (resp.get("response_metadata") or {}).get("next_cursor") or None
        if not cursor:
            break
    return "\n".join(out) if out else f"(no channels matching '{query}')"


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

    # While out of usage credits, stay completely silent — the outage was
    # already announced once when the limit was first hit.
    if _limit_paused():
        logger.info(f"Usage-limit pause active — ignoring message in {channel} (thread {thread_ts})")
        return

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

    # Prepend sender attribution so Claude knows who sent this message
    sender_name = _get_user_name(user_id)
    msg_ts = event.get("ts")

    # Cross-thread forwarding: if a reply landed in a thread that's been
    # registered as a forward (e.g., a DM Claude opened mid-task to ask
    # someone a question), rewrite the routing so the reply is delivered
    # into the original conversation with attribution. The eyes reaction
    # below still goes on the original message in its original channel.
    reaction_channel = channel
    reaction_msg_ts = msg_ts
    forward = _get_forward(thread_ts)
    if forward:
        original_thread = thread_ts
        text = (
            f"[{sender_name} ({user_id}) replied in DM thread {original_thread}]:\n"
            f"{text}"
        )
        thread_ts = forward["thread"]
        channel = forward["channel"]
        if forward.get("user_id"):
            user_id = forward["user_id"]
        _remove_forward(original_thread)
        logger.info(
            f"Forwarded reply from {sender_name} in {original_thread} -> {thread_ts}"
        )

    # For channel messages (not DMs), let Claude decide if it should respond
    is_channel = event.get("channel_type") not in ("im", "mpim")
    # Backend-aware: a Codex-backed thread has its saved thread id / live
    # process in the codex registries, not the Claude ones. Consult both so
    # in-thread follow-ups on Codex rooms aren't treated as cold contact.
    has_existing_session = (
        _get_session(thread_ts) is not None
        or bot_codex._load_thread_id(thread_ts) is not None
    )

    # Check if there's already a live process for this thread
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

    channel_type = event.get("channel_type", "")
    if not _channel_allowed(channel, channel_type):
        logger.info(f"Ignoring message in non-allowed channel {channel} ({_get_channel_name(channel)})")
        return

    # Inject the SKIP relevance filter for every message except 1:1 DMs.
    # 1:1 DM = always respond; any multi-person space (group DM, private or
    # public channel) = only respond when directly addressed.
    is_dm = channel_type == "im"

    # In public channels, private channels, and group DMs, count inbound messages
    # per thread so we can re-inject a shorter relevance reminder every
    # REMINDER_EVERY messages — Claude forgets the "only respond when addressed"
    # rule once a thread is long.
    is_reminder_space = channel_type in ("channel", "group", "mpim")
    show_reminder = False
    if is_reminder_space:
        with _live_sessions_lock:
            _thread_msg_counts[thread_ts] = _thread_msg_counts.get(thread_ts, 0) + 1
            count = _thread_msg_counts[thread_ts]
        # Only inside an ongoing thread — cold contact already gets the full filter.
        if (has_existing_session or has_live_process) and count % REMINDER_EVERY == 0:
            show_reminder = True

    prefix = ""
    if not is_dm and not has_existing_session and not has_live_process:
        channel_name = _get_channel_name(channel)
        prefix = (
            f"A new message in #{channel_name}. "
            "Only respond if you're directly addressed by your name 'Andy' or tagged "
            "or if you're already part of the conversation thread. "
            "Respond with exactly \"SKIP\" in ALL other cases. "
            "Don't say 'Skipping this as it's not relevant' or 'Nothing for me to do here' "
            "or anything like it. Just be precise and say exactly \"SKIP\" — "
            "because that will result in the harness not showing your msg "
            "at all in Slack, which is the correct behaviour.\n\n"
        )
    elif show_reminder:
        channel_name = _get_channel_name(channel)
        prefix = (
            f"[Reminder: #{channel_name} is a shared, multi-person space.] "
            "Only respond if you're directly addressed by name 'Andy', tagged, or "
            "actively part of this exchange. In all other cases respond with exactly "
            "\"SKIP\" and nothing else — that suppresses the message in Slack.\n\n"
        )

    if thread_context:
        text = prefix + f"{thread_context}\n\n[{sender_name}]({user_id}):\n{text}"
    else:
        text = prefix + f"[{sender_name}]({user_id}):\n{text}"

    # Add eyes reaction as thinking indicator
    try:
        slack_client.reactions_add(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
    except Exception:
        pass

    # Get or create a live Claude process for this thread
    all_texts = []
    first_text_sent = False
    skip_detected = False

    def on_text(text_block: str):
        """Called for each text block Claude produces — post it to Slack immediately."""
        nonlocal first_text_sent, skip_detected

        # Usage-limit notices are synthesized by the CLI, not the model.
        # Suppress them; announce the outage once and pause inbound handling.
        if LIMIT_RE.search(text_block):
            until_epoch = _enter_limit_pause(text_block)
            logger.warning(f"Usage limit hit in thread {thread_ts}: {text_block!r}")
            if until_epoch:
                until = datetime.fromtimestamp(until_epoch, timezone.utc)
                slack_client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text=(f"I've run out of usage credits — I'll be back around "
                          f"{until:%-I:%M%p} UTC. Anything sent before then won't get a reply."),
                )
            return

        # Check for SKIP on the very first text block (channel relevance filter)
        if not first_text_sent and text_block.strip() == "SKIP":
            skip_detected = True
            return

        all_texts.append(text_block)

        # Auto-upload any file paths mentioned
        _auto_upload_files(text_block, channel, thread_ts=thread_ts)

        # Post to Slack
        post_response(channel, text_block, thread_ts=thread_ts)
        first_text_sent = True

    start = time.time()

    # Dispatch: Codex-backed rooms route through bot_codex; every other room
    # falls through to the unchanged Claude path below. send_to_codex blocks
    # until the turn completes (its own turn_lock serializes send→wait, and
    # handles mid-turn follow-ups via turn/steer internally).
    if resolve_backend(channel, user_id) == "codex":
        try:
            codex_session = _get_or_create_codex_session(
                thread_ts=thread_ts, channel=channel, user_id=user_id, on_text=on_text,
            )
            bot_codex.send_to_codex(codex_session, text)
        except Exception as e:
            logger.error(f"Codex backend error in thread {thread_ts}: {e}")
            try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
            except Exception: pass
            slack_client.chat_postMessage(
                channel=channel, thread_ts=thread_ts,
                text=f"Something went wrong (Codex backend): {e}",
            )
            return
        try: slack_client.reactions_remove(channel=reaction_channel, name="eyes", timestamp=reaction_msg_ts)
        except Exception: pass
        if skip_detected:
            audit_skipped(event, time.time() - start, codex_session.codex_thread_id)
            logger.info(f"Skipped message from {user_id} in {channel} (not relevant)")
            return
        duration = time.time() - start
        audit_interaction(event, "\n\n".join(all_texts), duration, codex_session.codex_thread_id or "")
        logger.info(f"Codex turn done in {duration:.1f}s for thread {thread_ts}")
        return

    try:
        session = _get_or_create_live_session(thread_ts, channel, user_id=user_id)

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
        audit_skipped(event, duration, session.session_id)
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

    user_id = event.get("user", "")
    # Forwarded replies bypass the AUTHORIZED_USERS check: the bot itself
    # opened the DM, and the supervisor who authorized that DM is implicitly
    # authorizing the reply. Without this, replies from teammates who aren't
    # in AUTHORIZED_USERS would be rejected with a generic refusal.
    event_thread_ts = event.get("thread_ts") or event.get("ts")
    is_forwarded = _get_forward(event_thread_ts) is not None
    if not is_authorized(user_id) and not is_forwarded:
        # In DMs, block unauthorized users. In channels, let them through —
        # Claude will talk to anyone in public but respects info boundaries.
        if event.get("channel_type") in ("im", "mpim"):
            log_unauthorized(event)
            say(text="I only respond to authorized users.", thread_ts=event.get("ts"))
            return
        log_unauthorized(event)

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

    if not _channel_allowed(channel, event.get("channel_type", "")):
        logger.info(f"Ignoring mention in non-allowed channel {channel} ({_get_channel_name(channel)})")
        return

    event_thread_ts = event.get("thread_ts") or event.get("ts")
    is_forwarded = _get_forward(event_thread_ts) is not None
    if not is_authorized(user_id) and not is_forwarded:
        # In DMs, block. In channels, let through (Claude respects info boundaries).
        if event.get("channel_type") in ("im", "mpim"):
            log_unauthorized(event)
            say(text="I only respond to authorized users.", thread_ts=event.get("ts"))
            return
        log_unauthorized(event)

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
# Interactive actions (Block Kit buttons)
# ---------------------------------------------------------------------------


@app.action("vote_strong")
def handle_vote_strong(ack, body):
    ack()
    user_id = body["user"]["id"]
    vote_key = body["actions"][0]["value"]
    threading.Thread(target=_handle_vote, args=("vote_strong", vote_key, user_id), daemon=True).start()


@app.action("vote_pass")
def handle_vote_pass(ack, body):
    ack()
    user_id = body["user"]["id"]
    vote_key = body["actions"][0]["value"]
    threading.Thread(target=_handle_vote, args=("vote_pass", vote_key, user_id), daemon=True).start()


# Registered after the vote handlers — Bolt dispatches to the first matching
# listener, so vote_* clicks never reach this catch-all.
@app.action(re.compile(r"^(?!vote_).*"))
def handle_block_action(ack, body):
    """Route button clicks / menu selections into the thread's Claude session.

    Any interactive element the bot (or Claude via the SDK) posts lands here.
    The click becomes a structured message in the same thread, so Claude sees
    '[Name clicked "Send it"]' and responds there. URL buttons are
    navigational — ack only.
    """
    ack()
    try:
        action = body["actions"][0]
        if action.get("url"):
            return

        user_id = body["user"]["id"]
        if not is_authorized(user_id):
            log_unauthorized(body)
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
            # "Andy" in the text keeps this from being SKIPped by the
            # channel-relevance filter when the click starts a fresh session
            "text": f"[Button click for Andy: {_get_user_name(user_id)} clicked {desc} "
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


@flask_app.route("/slack/actions", methods=["POST"])
def slack_actions():
    return handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "ai-employee"})


@flask_app.route("/internal/forward", methods=["POST"])
def register_forward_endpoint():
    """Register a cross-thread forward. Called by `bot.py --send --forward-to`.

    Localhost-only — same-machine CLI talking to the running server. Looks up
    the target thread's live session for channel + session_id + user_id and
    persists the forward to .forwards.json.
    """
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    from_thread = data.get("from_thread")
    to_thread = data.get("to_thread")
    if not from_thread or not to_thread:
        return jsonify({"error": "from_thread and to_thread required"}), 400
    with _live_sessions_lock:
        target = _live_sessions.get(to_thread)
        target_channel = target.channel if target else ""
        target_session_id = target.session_id if target else _get_session(to_thread)
        target_user_id = target.user_id if target else ""
    if not target_channel:
        return jsonify({
            "error": "no_live_session",
            "detail": f"no live session for thread {to_thread} — forward requires the target to be alive at registration",
        }), 404
    _add_forward(
        from_thread=from_thread,
        to_thread=to_thread,
        to_channel=target_channel,
        session_id=target_session_id,
        user_id=target_user_id,
    )
    logger.info(f"Registered forward: {from_thread} -> {to_thread}")
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
        "--channel", nargs=2, metavar=("CHANNEL", "MESSAGE"),
        help="Post a message to a channel and exit",
    )
    parser.add_argument(
        "--history", metavar="CHANNEL_ID",
        help="Print recent messages from a channel (or a thread if --thread is set)",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Max messages to return for --history (default 50)",
    )
    parser.add_argument(
        "--find-channel", metavar="QUERY",
        help="List channels whose name contains QUERY (case-insensitive)",
    )
    parser.add_argument(
        "--with-votes", action="store_true",
        help="Post the message with Block Kit voting buttons (use with --channel or --send)",
    )
    parser.add_argument(
        "--forward-to", metavar="THREAD_TS", dest="forward_to",
        help="When a reply lands in this new DM thread, route it into the live session for THREAD_TS instead of starting a new conversation. Requires the running bot server to have a live session for THREAD_TS.",
    )
    parser.add_argument(
        "--session-id", metavar="SESSION_ID", dest="session_id",
        help="Register this Claude session_id as the resume target for replies in this DM thread. Use for cron jobs that DM someone, exit, and want to continue where they left off when the person replies.",
    )
    args = parser.parse_args()

    # CLI modes — send and exit
    if args.send:
        if args.with_votes:
            response = slack_client.conversations_open(users=[args.send[0]])
            channel_id = response["channel"]["id"]
            ts = post_with_votes(channel_id, args.send[1], thread_ts=args.thread)
            if ts:
                print(ts)
        else:
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
        if args.with_votes:
            ts = post_with_votes(args.channel[0], args.channel[1], thread_ts=args.thread)
            if ts:
                print(ts)
        else:
            send_to_channel(args.channel[0], args.channel[1], thread_ts=args.thread)
        return

    if args.history:
        print(fetch_channel_history(args.history, limit=args.limit, thread_ts=args.thread))
        return

    if args.find_channel:
        print(find_channel(args.find_channel))
        return

    # Server mode
    if not SLACK_BOT_TOKEN or not SLACK_SIGNING_SECRET:
        logger.error("Missing SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET in .env")
        raise SystemExit(1)

    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    logger.info(f"{BOT_DISPLAY_NAME} starting on port {PORT}")
    logger.info(f"Authorized users: {AUTHORIZED_USERS or 'all'}")
    logger.info(f"Allowed channel substrings: {ALLOWED_CHANNEL_SUBSTRINGS or '(all channels)'}")
    logger.info(f"Project dir: {PROJECT_DIR}")

    # Garbage-collect stale forward entries (>14 days old) from prior runs
    _gc_forwards()

    # Start idle session cleanup thread
    threading.Thread(target=_cleanup_idle_sessions, daemon=True).start()

    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
