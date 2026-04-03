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
PROJECT_DIR = os.environ.get("PROJECT_DIR", "")
if not PROJECT_DIR:
    logger.error("PROJECT_DIR not set. Add it to .env")
    raise SystemExit(1)

CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "1800"))  # 30 min default
MAX_SLACK_MSG_LEN = 3900
PORT = int(os.environ.get("PORT", "3000"))

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
            lines.append(f"[You ({BOT_DISPLAY_NAME})] said:\n{msg_text}")
        else:
            name = _get_user_name(msg_user)
            lines.append(f"[{name}] said:\n{msg_text}")

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
# Live session management: long-lived Claude processes with stream-json I/O
#
# Instead of spawning a new `claude -p` subprocess for every message (which
# causes race conditions when multiple messages arrive for the same thread),
# we keep Claude processes alive and pipe messages to their stdin as JSON.
# The CLI queues them automatically, matching terminal behavior.
# ---------------------------------------------------------------------------

IDLE_TIMEOUT = 1800  # 30 minutes — kill process if no messages
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
    # Serializes the full send→wait cycle so only one message at a time
    # is being actively processed. Other messages queue in our Python code.
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    # Callback for posting text blocks to Slack
    _on_text: callable = field(default=None, repr=False)
    # Event that signals when a turn (result) is complete
    _turn_done: threading.Event = field(default_factory=threading.Event)


# thread_ts → LiveSession
_live_sessions: dict[str, LiveSession] = {}
_live_sessions_lock = threading.Lock()


def _spawn_claude_process(session_id: str | None = None) -> subprocess.Popen:
    """Spawn a long-lived Claude CLI process with stream-json I/O."""
    cmd = [
        "claude",
        "-p", "",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--model", "claude-opus-4-6[1m]",
        "--effort", "medium",
    ]
    if session_id:
        cmd.extend(["--resume", session_id])

    stderr_tmp = tempfile.NamedTemporaryFile(
        mode="w+", suffix=".stderr", delete=False
    )

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_tmp,
        text=True,
        cwd=PROJECT_DIR,
    )
    logger.info(f"Spawned Claude process pid={proc.pid} (resume={session_id or 'none'})")
    return proc


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

            msg_type = data.get("type")

            if msg_type == "system":
                sid = data.get("session_id")
                if sid:
                    session.session_id = sid

            elif msg_type == "assistant":
                content = data.get("message", {}).get("content", [])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and session._on_text:
                            session._on_text(text)

            elif msg_type == "result":
                sid = data.get("session_id")
                if sid:
                    session.session_id = sid
                    _save_session(session.thread_ts, sid)
                session._turn_done.set()

    except Exception as e:
        logger.error(f"Reader loop error for thread {session.thread_ts}: {e}")
    finally:
        # Process ended — unblock any thread waiting on a response
        session._turn_done.set()
        logger.info(f"Reader loop ended for thread {session.thread_ts} (pid={session.proc.pid})")
        with _live_sessions_lock:
            _live_sessions.pop(session.thread_ts, None)


def _get_or_create_live_session(thread_ts: str, channel: str) -> LiveSession:
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
        proc = _spawn_claude_process(session_id=saved_session_id)
        session = LiveSession(
            proc=proc,
            session_id=saved_session_id,
            channel=channel,
            thread_ts=thread_ts,
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
) -> str | None:
    """Send a proactive DM. Returns thread_ts."""
    response = slack_client.conversations_open(users=[user_id])
    channel_id = response["channel"]["id"]

    slack_text = md_to_slack(message)
    chunks = chunk_message(slack_text)

    parent_ts = thread_ts
    for chunk in chunks:
        result = slack_client.chat_postMessage(
            channel=channel_id, text=chunk, thread_ts=parent_ts,
        )
        if parent_ts is None:
            parent_ts = result["ts"]

    effective_thread_ts = thread_ts or parent_ts

    # Auto-upload any file paths mentioned in the message
    _auto_upload_files(message, channel_id, thread_ts=effective_thread_ts)

    if session_id and effective_thread_ts:
        _save_session(effective_thread_ts, session_id)

    audit_logger.info(
        f"PROACTIVE_DM | USER:{user_id} | CHANNEL:{channel_id} "
        f"| THREAD:{effective_thread_ts} | SESSION:{session_id or 'none'} "
        f"| MSG_LEN:{len(message)}"
    )
    return effective_thread_ts


def send_to_channel(
    channel: str,
    message: str,
    session_id: str | None = None,
    thread_ts: str | None = None,
) -> str | None:
    """Post a message to a channel (optionally in a thread). Returns thread_ts."""
    slack_text = md_to_slack(message)
    chunks = chunk_message(slack_text)

    parent_ts = thread_ts
    for chunk in chunks:
        result = slack_client.chat_postMessage(
            channel=channel, text=chunk, thread_ts=parent_ts,
        )
        if parent_ts is None:
            parent_ts = result["ts"]

    effective_thread_ts = thread_ts or parent_ts

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

    # Strip bot mention
    text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

    # Download attachments
    attached_files = download_slack_files(event)

    if not text and not attached_files:
        return

    if attached_files:
        file_instructions = [f"The user attached a file. Read it at: {fp}" for fp in attached_files]
        text = "\n".join(file_instructions) + "\n\n" + (text or "Describe what you see in the attached file(s).")

    # Prepend sender attribution so Claude knows who sent this message
    sender_name = _get_user_name(user_id)
    msg_ts = event.get("ts")

    # For channel messages (not DMs), let Claude decide if it should respond
    is_channel = event.get("channel_type") not in ("im", "mpim")
    has_existing_session = _get_session(thread_ts) is not None

    # Check if there's already a live process for this thread
    has_live_process = thread_ts in _live_sessions and _live_sessions[thread_ts].proc.poll() is None

    # If this is a thread reply and we have no saved session AND no live process,
    # fetch the full thread history so Claude has context on what was said before.
    is_thread_reply = thread_ts != msg_ts
    thread_context = None
    if not has_existing_session and not has_live_process and is_thread_reply:
        thread_context = _fetch_thread_context(channel, thread_ts, msg_ts)

    is_public_channel = event.get("channel_type") == "channel"
    if is_public_channel and not has_existing_session and not has_live_process:
        prefix = (
            f"You received this message in a public channel from {sender_name} (<@{user_id}>). "
            "Only respond if you are directly addressed by name, asked a question, or given an explicit task. "
            "If the message is general discussion, status updates, or chatter — even if it relates to your work — respond with exactly: SKIP\n\n"
        )
        if thread_context:
            text = prefix + f"Here is the conversation so far in this thread:\n\n{thread_context}\n\n[{sender_name}] now says:\n{text}"
        else:
            text = prefix + text
    else:
        if thread_context:
            text = f"Here is the conversation so far in this thread:\n\n{thread_context}\n\n[{sender_name}] now says:\n{text}"
        else:
            text = f"[{sender_name}] says:\n{text}"

    # Add eyes reaction as thinking indicator
    try:
        slack_client.reactions_add(channel=channel, name="eyes", timestamp=msg_ts)
    except Exception:
        pass

    # Get or create a live Claude process for this thread
    all_texts = []
    first_text_sent = False
    skip_detected = False

    def on_text(text_block: str):
        """Called for each text block Claude produces — post it to Slack immediately."""
        nonlocal first_text_sent, skip_detected

        # Check for SKIP on the very first text block (channel relevance filter)
        if not first_text_sent and text_block.strip() == "SKIP":
            skip_detected = True
            return

        all_texts.append(text_block)

        # Auto-upload any file paths mentioned
        _auto_upload_files(text_block, channel, thread_ts=thread_ts)

        # Post to Slack
        slack_text = md_to_slack(text_block)
        for chunk in chunk_message(slack_text):
            slack_client.chat_postMessage(
                channel=channel, text=chunk, thread_ts=thread_ts,
            )
        first_text_sent = True

    start = time.time()
    try:
        session = _get_or_create_live_session(thread_ts, channel)

        # Acquire turn_lock — this serializes the send→wait cycle.
        # If another message is already being processed, we block here.
        with session.turn_lock:
            session._on_text = on_text
            session._turn_done.clear()

            _send_to_claude(session, text)

            if not session._turn_done.wait(timeout=CLAUDE_TIMEOUT):
                try: slack_client.reactions_remove(channel=channel, name="eyes", timestamp=msg_ts)
                except Exception: pass
                minutes = CLAUDE_TIMEOUT // 60
                slack_client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text=f"Sorry, that timed out after {minutes} minutes. Try a simpler question?",
                )
                return

            # Check if the process died without producing a response
            if not all_texts and not skip_detected and session.proc.poll() is not None:
                try: slack_client.reactions_remove(channel=channel, name="eyes", timestamp=msg_ts)
                except Exception: pass
                logger.error(f"Claude process died without responding in thread {thread_ts}")
                slack_client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text="Sorry, I lost my train of thought. Could you try sending that again?",
                )
                return

    except Exception as e:
        try: slack_client.reactions_remove(channel=channel, name="eyes", timestamp=msg_ts)
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
        try: slack_client.reactions_remove(channel=channel, name="eyes", timestamp=msg_ts)
        except Exception: pass
        logger.info(f"Skipped message from {user_id} in {channel} (not relevant)")
        return

    # Remove eyes reaction
    try:
        slack_client.reactions_remove(channel=channel, name="eyes", timestamp=msg_ts)
    except Exception:
        pass

    full_response = "\n\n".join(all_texts)
    audit_interaction(event, full_response, duration, session.session_id)


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
    if not is_authorized(user_id):
        # In DMs, block unauthorized users. In channels, let them through —
        # Claude will talk to anyone in public but respects info boundaries.
        if event.get("channel_type") in ("im", "mpim"):
            log_unauthorized(event)
            say(text="I only respond to authorized users.", thread_ts=event.get("ts"))
            return
        log_unauthorized(event)

    # Process async — return immediately so Slack gets its 200
    threading.Thread(target=process_message_async, args=(event,), daemon=True).start()


@app.event("app_mention")
def handle_mention(event, say):
    """Handle @bot mentions in channels."""
    user_id = event.get("user", "")
    if not is_authorized(user_id):
        # In DMs, block. In channels, let through (Claude respects info boundaries).
        if event.get("channel_type") in ("im", "mpim"):
            log_unauthorized(event)
            say(text="I only respond to authorized users.", thread_ts=event.get("ts"))
            return
        log_unauthorized(event)

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
# Flask app (HTTP Events API)
# ---------------------------------------------------------------------------

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "bot": "ai-employee"})


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
    args = parser.parse_args()

    # CLI modes — send and exit
    if args.send:
        thread_ts = send_dm(args.send[0], args.send[1], thread_ts=args.thread)
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
        send_to_channel(args.channel[0], args.channel[1], thread_ts=args.thread)
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

    # Start idle session cleanup thread
    threading.Thread(target=_cleanup_idle_sessions, daemon=True).start()

    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
