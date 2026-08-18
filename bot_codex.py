"""Codex backend for the Slack bot — JSON-RPC client over `codex app-server` stdio.

The bot normally drives Claude Code's CLI (see `_spawn_claude_process` in
bot.py). This module is an alternate *backend*: it drives OpenAI's
`codex app-server` over JSON-RPC on stdio instead. The Slack event loop stays
identical — a room whose model-config entry sets `"backend": "codex"` routes
here, everything else falls through to Claude.

Shape mirrors bot.py's LiveSession: one long-lived `codex app-server`
subprocess per Slack thread; turns flow via thread/start + turn/start; mid-turn
follow-ups via turn/steer; output streams to Slack via a caller-supplied
on_text callback. bot.py imports this lazily only when a codex-backed room gets
a message, so users who never touch Codex pay nothing.

Requires the `codex` CLI on PATH (https://github.com/openai/codex) and a Codex
account. Set CODEX_HOME in the environment to isolate the bot's Codex state
from your interactive `codex` sessions; leave it unset to share the default.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("bot.codex")

# Optional: point the bot's Codex at a dedicated home so it doesn't share
# threads/auth with your interactive `codex`. Unset → codex uses its default.
CODEX_HOME = os.environ.get("CODEX_HOME", "")
# Fallback model when a room's model-config entry names no model. The
# app-server ignores config.toml's `model` key (it uses the account default),
# so the model must be set per-thread in thread/start. Reasoning effort, by
# contrast, IS honored from config.toml (model_reasoning_effort = "high").
DEFAULT_CODEX_MODEL = os.environ.get("CODEX_MODEL", "gpt-5.6-sol")
# Equivalent of Claude's `--dangerously-skip-permissions` /
# codex's `--dangerously-bypass-approvals-and-sandbox`: never prompt for
# approval and run without a sandbox (full network + filesystem). Required so
# Slack-driven turns don't stall on approval requests there's no human to
# answer (e.g. network-dependent tool calls that a sandbox would block).
CODEX_APPROVAL_POLICY = "never"            # AskForApproval enum
CODEX_SANDBOX_MODE = "danger-full-access"  # SandboxMode enum
SESSION_DIR = Path.home() / ".claude-home-base" / "codex-sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
TURN_TIMEOUT = 600  # 10 min per turn
INIT_TIMEOUT = 15
REQUEST_TIMEOUT = 30


@dataclass
class CodexSession:
    """A long-lived `codex app-server` subprocess attached to a Slack thread."""
    proc: subprocess.Popen
    thread_ts: str
    channel: str
    user_id: str
    codex_thread_id: Optional[str] = None
    current_turn_id: Optional[str] = None
    stdin_lock: threading.Lock = field(default_factory=threading.Lock)
    turn_lock: threading.Lock = field(default_factory=threading.Lock)
    last_activity: float = field(default_factory=time.time)
    _on_text: Optional[Callable[[str], None]] = field(default=None, repr=False)
    _on_status: Optional[Callable[[str], None]] = field(default=None, repr=False)
    _next_id: int = 100
    _id_lock: threading.Lock = field(default_factory=threading.Lock)
    _pending: dict = field(default_factory=dict)
    _pending_events: dict = field(default_factory=dict)
    _turn_done: threading.Event = field(default_factory=threading.Event)
    _last_usage: dict = field(default_factory=dict)
    _agent_buffer: list = field(default_factory=list)  # current turn's tokens

    def next_id(self) -> int:
        with self._id_lock:
            n = self._next_id
            self._next_id += 1
            return n


def _session_file(thread_ts: str) -> Path:
    return SESSION_DIR / f"{thread_ts}.json"


def _save_thread_id(thread_ts: str, codex_thread_id: str) -> None:
    _session_file(thread_ts).write_text(json.dumps({"codex_thread_id": codex_thread_id}))


def _load_thread_id(thread_ts: str) -> Optional[str]:
    p = _session_file(thread_ts)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("codex_thread_id")
    except Exception:
        return None


def spawn_codex_session(
    thread_ts: str,
    channel: str,
    user_id: str,
    on_text: Callable[[str], None],
    on_status: Optional[Callable[[str], None]] = None,
    model: Optional[str] = None,
    cwd: Optional[str] = None,
) -> CodexSession:
    """Spawn a codex app-server process and complete the JSON-RPC handshake.

    model: the Codex model to run (per-room, from model-config.json). Falls
        back to DEFAULT_CODEX_MODEL.
    cwd:   working directory the agent operates in. Defaults to the user's home,
        matching the "full access to your machine" posture of the Claude path.
    """
    model = model or DEFAULT_CODEX_MODEL
    cwd = cwd or str(Path.home())
    env = {**os.environ}
    if CODEX_HOME:
        env["CODEX_HOME"] = CODEX_HOME
    proc = subprocess.Popen(
        ["codex", "app-server", "--listen", "stdio://"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
        cwd=cwd,
    )
    session = CodexSession(
        proc=proc, thread_ts=thread_ts, channel=channel, user_id=user_id,
        _on_text=on_text, _on_status=on_status,
    )
    threading.Thread(target=_reader_loop, args=(session,), daemon=True).start()
    threading.Thread(target=_stderr_drain, args=(session,), daemon=True).start()

    # Handshake
    init_result = _rpc_request(session, "initialize", {
        "clientInfo": {"name": "claude-home-base-codex", "version": "0.1"},
        "protocolVersion": "1.0",
    }, timeout=INIT_TIMEOUT)
    if not init_result or "error" in init_result:
        raise RuntimeError(f"Codex initialize failed: {init_result}")
    _rpc_notify(session, "initialized")

    # Resume or start
    existing = _load_thread_id(thread_ts)
    if existing:
        resp = _rpc_request(session, "thread/resume", {
            "threadId": existing,
            "cwd": cwd,
            "approvalPolicy": CODEX_APPROVAL_POLICY,
            "sandbox": CODEX_SANDBOX_MODE,
        })
        if resp and "error" not in resp:
            session.codex_thread_id = existing
            logger.info(f"Codex thread resumed {existing} for slack thread {thread_ts}")
        else:
            logger.warning(f"thread/resume failed for {existing}, starting fresh: {resp}")
            existing = None
    if not existing:
        resp = _rpc_request(session, "thread/start", {
            "cwd": cwd,
            "ephemeral": False,
            "model": model,
            "approvalPolicy": CODEX_APPROVAL_POLICY,
            "sandbox": CODEX_SANDBOX_MODE,
        })
        if not resp or "error" in resp:
            raise RuntimeError(f"thread/start failed: {resp}")
        session.codex_thread_id = resp["result"]["thread"]["id"]
        _save_thread_id(thread_ts, session.codex_thread_id)
        logger.info(f"Codex thread started {session.codex_thread_id} for slack thread {thread_ts}")

    return session


def send_to_codex(session: CodexSession, text: str) -> None:
    """Send a user message to the running Codex session.

    If a turn is in flight, use turn/steer. Otherwise, turn/start.
    Blocks until the turn completes (turn_done event set).
    """
    with session.turn_lock:
        session.last_activity = time.time()
        session._turn_done.clear()
        session._agent_buffer = []
        params_input = [{"type": "text", "text": text}]

        if session.current_turn_id:
            # Mid-turn steer
            _rpc_request(session, "turn/steer", {
                "threadId": session.codex_thread_id,
                "expectedTurnId": session.current_turn_id,
                "input": params_input,
            })
        else:
            resp = _rpc_request(session, "turn/start", {
                "threadId": session.codex_thread_id,
                "input": params_input,
            })
            if resp and "result" in resp:
                session.current_turn_id = resp["result"].get("turn", {}).get("id")

        if not session._turn_done.wait(timeout=TURN_TIMEOUT):
            logger.error(f"Codex turn timed out after {TURN_TIMEOUT}s in thread {session.thread_ts}")
            if session._on_text:
                session._on_text(f":warning: Codex turn timed out after {TURN_TIMEOUT//60}min")


def shutdown(session: CodexSession) -> None:
    try:
        session.proc.stdin.close()
    except Exception:
        pass
    try:
        session.proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        session.proc.kill()


# ---------------------------------------------------------------------------
# Internal — JSON-RPC plumbing
# ---------------------------------------------------------------------------

def _rpc_send(session: CodexSession, payload: dict) -> None:
    line = json.dumps(payload) + "\n"
    with session.stdin_lock:
        session.proc.stdin.write(line)
        session.proc.stdin.flush()


def _rpc_request(session: CodexSession, method: str, params: dict,
                 timeout: float = REQUEST_TIMEOUT) -> Optional[dict]:
    rid = session.next_id()
    session._pending[rid] = []
    session._pending_events[rid] = threading.Event()
    _rpc_send(session, {"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    if not session._pending_events[rid].wait(timeout=timeout):
        logger.warning(f"RPC {method} timeout (id={rid})")
        return None
    return session._pending[rid][0] if session._pending[rid] else None


def _rpc_notify(session: CodexSession, method: str, params: dict = None) -> None:
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    _rpc_send(session, msg)


def _rpc_respond(session: CodexSession, request_id, result: dict) -> None:
    _rpc_send(session, {"jsonrpc": "2.0", "id": request_id, "result": result})


def _stderr_drain(session: CodexSession) -> None:
    for line in session.proc.stderr:
        s = line.rstrip()
        if not s:
            continue
        if "ERROR" in s or "WARN" in s:
            logger.warning(f"[codex-stderr] {s[:300]}")


def _reader_loop(session: CodexSession) -> None:
    """Read JSON-RPC messages from codex stdout and dispatch."""
    try:
        for line in session.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"non-JSON from codex: {line[:200]}")
                continue
            _dispatch(session, data)
    except Exception as e:
        logger.error(f"Codex reader loop crashed: {e}")
    finally:
        session._turn_done.set()
        logger.info(f"Codex reader loop ended (pid={session.proc.pid}, slack thread={session.thread_ts})")


def _dispatch(session: CodexSession, data: dict) -> None:
    # JSON-RPC response (has id + result/error, no method)
    if "id" in data and ("result" in data or "error" in data) and "method" not in data:
        rid = data["id"]
        if rid in session._pending:
            session._pending[rid].append(data)
            session._pending_events[rid].set()
        return

    method = data.get("method", "")
    params = data.get("params", {})

    # Server-to-client requests (need a response)
    if "id" in data and "method" in data:
        _handle_server_request(session, data["id"], method, params)
        return

    # Notifications
    if method == "item/agentMessage/delta":
        delta = params.get("delta") or params.get("text", "")
        if delta:
            session._agent_buffer.append(delta)
            # We don't post per-token to Slack (too chatty) — post on item completion below
    elif method == "item/completed":
        item = params.get("item", {})
        itype = item.get("type") or item.get("itemType")
        if itype == "agentMessage":
            full_text = "".join(session._agent_buffer).strip()
            session._agent_buffer = []
            if full_text and session._on_text:
                session._on_text(full_text)
        elif itype in ("commandExecution", "fileChange", "reasoning") and session._on_status:
            session._on_status(itype)
    elif method == "turn/started":
        tid = params.get("turnId") or params.get("id")
        if tid:
            session.current_turn_id = tid
    elif method == "turn/completed":
        session._last_usage = params.get("usage", {})
        session.current_turn_id = None
        session._turn_done.set()
    elif method == "thread/tokenUsage/updated":
        session._last_usage = params
    elif method == "error":
        logger.error(f"Codex error notification: {params}")
        if session._on_text:
            session._on_text(f":warning: Codex error: {params.get('message', params)}")
        session._turn_done.set()


def _handle_server_request(session: CodexSession, request_id, method: str, params: dict) -> None:
    """Respond to server-initiated requests (approvals, tool input prompts).

    With CODEX_APPROVAL_POLICY="never" + CODEX_SANDBOX_MODE="danger-full-access"
    the app-server should not emit any of these approval requests. These
    branches are defense-in-depth, and each must use the *exact* response shape
    for its request type — the v2 `item/*` requests use different decision enums
    (and the permissions request wants a grant object, not a decision) than the
    legacy `execCommandApproval`/`applyPatchApproval` requests. A malformed
    response is treated as a denial, which silently blocks the tool call.
    """
    if method in ("execCommandApproval", "applyPatchApproval"):
        # Legacy v1 ReviewDecision
        _rpc_respond(session, request_id, {"decision": "approved"})
    elif method in ("item/commandExecution/requestApproval",
                    "item/fileChange/requestApproval"):
        # v2 CommandExecution/FileChange approval decision
        _rpc_respond(session, request_id, {"decision": "accept"})
    elif method == "item/permissions/requestApproval":
        # v2 permissions grant — hand back a full-access profile for the session
        _rpc_respond(session, request_id, {
            "permissions": {
                "fileSystem": {
                    "entries": [{
                        "access": "write",
                        "path": {"type": "special", "value": {"kind": "root"}},
                    }],
                },
                "network": {"enabled": True},
            },
            "scope": "session",
        })
    elif method == "item/tool/requestUserInput":
        # No interactive user input available in Slack flow — cancel
        _rpc_respond(session, request_id, {"decision": "cancelled"})
    else:
        # Unknown server request — log and reject
        logger.warning(f"Unhandled server request {method}, rejecting")
        _rpc_respond(session, request_id, {"decision": "denied"})
