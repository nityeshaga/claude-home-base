#!/usr/bin/env python3
"""Voice bridge: browser mic  <->  OpenAI GPT-Live-1  <->  your AI (a Claude Code session).

Shape mirrors the Slack bot's session layer. A delegation event from GPT-Live plays the
role a Slack message plays: one user turn into a long-lived `claude -p` stream-json
process. If a turn is already running, the message is written to stdin anyway and the CLI
steers the running turn at its next tool-call boundary (same as the bot).

Design notes: README.md
Prompts:      ./prompts.md (parsed at call start; edit freely, no restart)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import websockets
from dotenv import load_dotenv
from slack_sdk import WebClient
from websockets.asyncio.server import serve

HERE = Path(__file__).resolve().parent
CALLS_DIR = HERE / "calls"   # one JSONL per call: every transcript line, delegation, append, tool call, text block
CALLS_DIR.mkdir(exist_ok=True)
HOME = Path.home()
load_dotenv(HERE / ".env")
# The Slack bot this bridge pairs with (bot.py from this repo). Its .env holds SLACK_BOT_TOKEN and its
# .sessions.json maps thread_ts -> Claude session id, so a reply in the call's thread resumes the call.
BOT_DIR = Path(os.environ.get("SLACK_BOT_DIR", HOME / "Projects" / "slack-bot")).expanduser()
load_dotenv(BOT_DIR / ".env")

PORT = int(os.environ.get("VOICE_BRIDGE_PORT", "9443"))
OPENAI_KEY = os.environ["OPENAI_API_KEY"]
SLACK = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
CLAUDE = os.path.expanduser(os.environ.get("CLAUDE_BIN") or shutil.which("claude") or str(HOME / ".local" / "bin" / "claude"))
CLAUDE_MODEL = os.environ.get("VOICE_CLAUDE_MODEL", "claude-opus-5")
CLAUDE_EFFORT = os.environ.get("VOICE_CLAUDE_EFFORT", "low")
LIVE_URI = "wss://api.openai.com/v1/live/sessions"
LIVE_VOICE = os.environ.get("VOICE_LIVE_VOICE", "stone")
VOICES = ["marin","quartz","ripple","vesper","willow","stone","gleam","meridian","bossa","tempo","beacon","delta","cinder"]
# Optional fast path (VOICE_FAST_FACTS=1): a search CLI that prints a JSON list of {source, title, snippet}.
# Defaults to this repo's search/ (see ../search/README.md).
SEARCH_PY = Path(os.environ.get("VOICE_SEARCH_PY", HOME / "claude-home-base" / "search" / "venv" / "bin" / "python3")).expanduser()
SEARCH_SCRIPT = Path(os.environ.get("VOICE_SEARCH_SCRIPT", HOME / "claude-home-base" / "search" / "luoji_search.py")).expanduser()
STATE_FILE = HERE / "state.json"          # learned device -> caller map
BOT_SESSIONS = BOT_DIR / ".sessions.json"  # thread_ts -> session id (so thread replies resume us)
APPEND_CHAR_CAP = 1800                     # ~500 tokens; GPT-Live rejects more per append
PROCESS_LINGER = 600                       # keep claude alive this long after hangup
PARK_SECONDS = 90                          # keep a call warm after the browser drops (screen lock, network blip)
PARKED: dict[str, "Call"] = {}
FAST_FACTS = os.environ.get("VOICE_FAST_FACTS", "0") == "1"  # off by default: the voice model once read retrieved notes aloud as if they were the answer

AGENT_NAME = os.environ.get("VOICE_AGENT_NAME", "Jarvis")  # how the assistant is named on the call and in prompts


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# callers.json: {"U0AAAAAAA": "Alice", ...} Slack user id -> first name. The first entry is the default
# caller when neither ?user= nor the learned device map says who is on the line.
USERS: dict[str, str] = _read_json(HERE / "callers.json")
if not USERS:
    sys.exit("callers.json is missing or empty: copy callers.json.example and fill in Slack user ids")
DEFAULT_USER = os.environ.get("VOICE_DEFAULT_USER", next(iter(USERS)))

(HERE / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler(HERE / "logs" / "bridge.log")],
)
log = logging.getLogger("bridge")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def load_prompts() -> dict[str, str]:
    text = (HERE / "prompts.md").read_text()
    out: dict[str, str] = {}
    for m in re.finditer(r"^## ([\w-]+)\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        body = m.group(2).strip()
        body = re.sub(r"\n---\s*$", "", body).strip()
        out[m.group(1)] = body
    return out


def fill(t: str, **kw) -> str:
    for k, v in kw.items():
        t = t.replace("{" + k + "}", str(v))
    return t


def chunks(s: str, n: int = APPEND_CHAR_CAP) -> list[str]:
    s = s.strip()
    if not s:
        return []
    out, cur = [], ""
    for para in re.split(r"(?<=[.!?])\s+", s):
        if len(cur) + len(para) + 1 > n and cur:
            out.append(cur)
            cur = para
        else:
            cur = (cur + " " + para).strip()
    if cur:
        out.append(cur)
    return [c[:n] for c in out]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def device_user(ip: str) -> str | None:
    """Who owns this address? Learned the first time they pick their name on the page."""
    return _read_json(STATE_FILE).get("devices", {}).get(ip)


def remember_device(ip: str, user_id: str) -> None:
    st = _read_json(STATE_FILE)
    st.setdefault("devices", {})[ip] = user_id
    STATE_FILE.write_text(json.dumps(st, indent=1))


def save_claude_session(user_id: str, sid: str, thread_ts: str) -> None:
    # Register with the Slack bot so a reply in the call thread resumes this call's session.
    bs = _read_json(BOT_SESSIONS)
    bs[thread_ts] = sid
    BOT_SESSIONS.write_text(json.dumps(bs))


# ---------------------------------------------------------------------------
# Claude process (one fresh session per call; the call's Slack thread resumes it afterwards)
# ---------------------------------------------------------------------------

@dataclass
class ClaudeProc:
    proc: asyncio.subprocess.Process
    session_id: str | None
    turn_running: bool = False
    last_activity: float = field(default_factory=time.time)
    # last text block seen this turn: spoken as commentary when the turn ends
    pending_text: str | None = None
    turn_done: asyncio.Event = field(default_factory=asyncio.Event)


async def spawn_claude(session_id: str | None, system_prompt: str,
                       channel_id: str, thread_ts: str) -> ClaudeProc:
    cmd = [
        CLAUDE, "-p", "",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--effort", CLAUDE_EFFORT,
        "--model", CLAUDE_MODEL,
        "--append-system-prompt", system_prompt,
    ]
    if session_id:
        cmd += ["--resume", session_id]
    env = {**os.environ,
           "CLAUDE_THREAD_TS": thread_ts,
           "CLAUDE_CHANNEL_ID": channel_id,
           "CLAUDE_SESSION_ID": session_id or "",
           "VOICE_CALL": "1"}
    stderr = open(HERE / "logs" / f"claude-{thread_ts}.stderr", "a")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=stderr, cwd=str(HOME), env=env,
        limit=256 * 1024 * 1024)  # stream-json lines can carry whole images; default 64 KB crashed the reader
    log.info("spawned claude pid=%s resume=%s model=%s effort=%s",
             proc.pid, session_id, CLAUDE_MODEL, CLAUDE_EFFORT)
    return ClaudeProc(proc=proc, session_id=session_id)


# ---------------------------------------------------------------------------
# A call
# ---------------------------------------------------------------------------

class Call:
    def __init__(self, browser, user_id: str, voice: str = LIVE_VOICE):
        self.browser = browser
        self.user_id = user_id
        self.voice = voice if voice in VOICES else LIVE_VOICE
        self.caller = USERS.get(user_id, "the caller")
        self.prompts = load_prompts()
        self.live = None
        self.claude: ClaudeProc | None = None
        self.transcript: list[tuple[str, str]] = []   # (role, text)
        self.cur_in = ""    # partial caller utterance
        self.cur_out = ""   # partial voice-model utterance
        self.sent_upto = 0  # transcript index already handed to Claude
        self.channel_id = ""
        self.thread_ts = ""
        self.ended = False
        self.started = time.time()
        self._live_tasks: list[asyncio.Task] = []
        self.id = uuid.uuid4().hex[:12]
        self.hangup = False
        self._reattached = asyncio.Event()

    # --- Slack thread -------------------------------------------------------
    def open_thread(self) -> None:
        dm = SLACK.conversations_open(users=[self.user_id])
        self.channel_id = dm["channel"]["id"]
        now = datetime.now().strftime("%a %d %b, %H:%M")
        r = SLACK.chat_postMessage(
            channel=self.channel_id,
            text=f":telephone_receiver: Voice call started, {now}. Anything visual from the call lands in this thread. Replying here after the call continues the same session.")
        self.thread_ts = r["ts"]
        self.rec("start", call_id=self.id, caller=self.caller, user=self.user_id, channel=self.channel_id,
                 voice=self.voice, model=CLAUDE_MODEL, effort=CLAUDE_EFFORT, via=getattr(self, "via", ""))

    def rec(self, kind: str, **kw) -> None:
        """Append one event to this call's record (calls/<thread_ts>.jsonl): frontend (transcript,
        delegations, appends) and backend (tool calls, text blocks, turn results) on one timeline,
        so intermediate backend output is reviewable without posting it to the thread."""
        if not getattr(self, "thread_ts", None):
            return
        try:
            with open(CALLS_DIR / f"{self.thread_ts}.jsonl", "a") as f:
                f.write(json.dumps({"t": round(time.time(), 3), "kind": kind, **kw}, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning("call record failed: %s", e)

    def thread_link(self) -> str:
        ts = self.thread_ts.replace(".", "")
        return f"https://slack.com/archives/{self.channel_id}/p{ts}"

    def post(self, text: str) -> None:
        self.rec("slack_post", text=text)
        try:
            SLACK.chat_postMessage(channel=self.channel_id, thread_ts=self.thread_ts, text=text)
        except Exception as e:
            log.warning("slack post failed: %s", e)

    # --- Browser -------------------------------------------------------------
    async def to_browser(self, obj: dict) -> None:
        if self.browser is None:
            return
        try:
            await self.browser.send(json.dumps(obj))
        except Exception:
            pass

    async def greet_browser(self, resumed: bool = False) -> None:
        """Everything a (re)attached page needs to draw the call."""
        await self.to_browser({"type": "call", "id": self.id, "started_ms": int((time.time() - self.started) * 1000)})
        if self.thread_ts:
            await self.to_browser({"type": "thread", "url": self.thread_link()})
        await self.to_browser({"type": "caller", "user": self.user_id, "name": self.caller,
                               "via": {"device": "this device", "default": "default"}.get(getattr(self, "via", ""), "")})
        if resumed:
            lines = list(self.transcript)
            if self.cur_in.strip():
                lines.append(("caller", self.cur_in.strip()))
            if self.cur_out.strip():
                lines.append(("agent", self.cur_out.strip()))
            await self.to_browser({"type": "replay", "lines": lines[-80:]})
            await self.to_browser({"type": "status", "text": "listening"})

    async def attach(self, browser) -> None:
        """A new page socket for a parked call."""
        self.browser = browser
        PARKED.pop(self.id, None)
        log.info("call %s reattached", self.id)
        self.rec("reattached")
        await self.greet_browser(resumed=True)
        self._reattached.set()

    # --- GPT-Live ------------------------------------------------------------
    async def live_send(self, obj: dict) -> None:
        if self.live is None:
            return
        obj.setdefault("event_id", f"ev_{int(time.time()*1000)}")
        await self.live.send(json.dumps(obj))

    async def append(self, kind: str, content: str, delegation_id: str | None) -> None:
        """kind: thinking | commentary | instructions."""
        for i, c in enumerate(chunks(content)):
            await self.live_send({"type": f"session.{kind}.append",
                                  "delegation_id": delegation_id, "content": c})
            self.rec("append", channel=kind, delegation_id=delegation_id, content=c)
            log.info("append %s [%s] %s", kind, delegation_id, c[:120].replace("\n", " "))

    def live_config(self) -> dict:
        now = datetime.now()
        common = dict(date=now.strftime("%A %d %B %Y"), time=now.strftime("%H:%M"),
                      caller_name=self.caller, thread_link=self.thread_link(), agent_name=AGENT_NAME)
        return {
            "model": "gpt-live-1",
            "instructions": fill(self.prompts["live-instructions"], **common),
            "audio": {"format": {"type": "audio/pcm", "rate": 24000},
                      "output": {"voice": self.voice}},
            "delegation": {"type": "client"},
            "input": [{"type": "message", "role": "developer",
                       "content": [{"type": "input_text",
                                    "text": fill(self.prompts["seed-developer"], **common)}]}],
        }

    async def run_live(self) -> None:
        hdr = {"Authorization": f"Bearer {OPENAI_KEY}"}
        async with websockets.connect(LIVE_URI, additional_headers=hdr,
                                      max_size=None, open_timeout=20) as ws:
            self.live = ws
            await self.live_send({"type": "session.start", "session": self.live_config()})
            async for raw in ws:
                ev = json.loads(raw)
                t = ev.get("type")
                if t == "session.output_audio.delta":
                    if self.browser is not None:
                        try:
                            await self.browser.send(base64.b64decode(ev["delta"]))
                        except Exception:
                            pass
                elif t == "session.input_transcript.delta":
                    self.cur_in += ev.get("delta", "")
                    await self.to_browser({"type": "transcript", "role": "you",
                                           "text": self.cur_in, "partial": True})
                    if re.search(r"[.!?]\s*$", self.cur_in) or len(self.cur_in) > 400:
                        self._commit("caller")
                elif t == "session.output_transcript.delta":
                    # Caller finished speaking once the model starts answering.
                    if self.cur_in.strip():
                        self._commit("caller")
                    self.cur_out += ev.get("delta", "")
                    await self.to_browser({"type": "transcript", "role": "agent",
                                           "text": self.cur_out, "partial": True})
                    if re.search(r"[.!?]\s*$", self.cur_out) or len(self.cur_out) > 400:
                        self._commit("agent")
                elif t == "session.delegation.created":
                    d = ev.get("delegation", {})
                    asyncio.create_task(self.on_delegation(d.get("id"), ev.get("offset_ms")))
                elif t == "session.started":
                    log.info("live session %s", ev["session"]["id"])
                    self.rec("live_session", id=ev["session"]["id"])
                    await self.to_browser({"type": "status", "text": "connected"})
                    await self.greet_browser()
                elif t == "session.usage.updated":
                    await self.to_browser({"type": "usage", "seconds": ev.get("usage", {}).get("seconds")})
                elif t == "session.closed":
                    log.info("live closed: %s usage=%s", ev.get("reason"), ev.get("usage"))
                    self.rec("live_closed", reason=ev.get("reason"), usage=ev.get("usage"))
                    break
                elif t == "error":
                    log.error("live error: %s", json.dumps(ev)[:500])
                    await self.to_browser({"type": "status", "text": f"error: {ev.get('error', {}).get('message', '')}"})
        self.live = None

    def _commit(self, role: str) -> None:
        if role == "caller" and self.cur_in.strip():
            self.transcript.append(("caller", self.cur_in.strip()))
            self.rec("transcript", role="caller", text=self.cur_in.strip())
            self.cur_in = ""
        elif role == "agent" and self.cur_out.strip():
            self.transcript.append(("agent", self.cur_out.strip()))
            self.rec("transcript", role="agent", text=self.cur_out.strip())
            self.cur_out = ""

    # --- Delegation = one user turn to Claude ---------------------------------
    async def on_delegation(self, delegation_id: str, offset_ms) -> None:
        # Include whatever the caller was mid-sentence on.
        if self.cur_in.strip():
            self._commit("caller")
        lines = self.transcript[self.sent_upto:]
        if not lines:
            lines = self.transcript[-4:]
        self.sent_upto = len(self.transcript)
        transcript = "\n".join(f"{self.caller if r == 'caller' else AGENT_NAME + ' (voice)'}: {t}" for r, t in lines)
        last_caller = next((t for r, t in reversed(lines) if r == "caller"), "")
        log.info("delegation %s @%sms: %s", delegation_id, offset_ms, last_caller[:120])
        self.rec("delegation", id=delegation_id, offset_ms=offset_ms, last_caller=last_caller, slice=transcript)
        await self.to_browser({"type": "status", "text": f"{AGENT_NAME} is thinking…"})
        self.post(f":speech_balloon: _{self.caller}:_ {last_caller}")

        # Fast path and Claude turn race; fast facts land first.
        if FAST_FACTS:
            asyncio.create_task(self.fast_facts(last_caller, delegation_id))
        await self.claude_turn(delegation_id, transcript)

    async def fast_facts(self, query: str, delegation_id: str) -> None:
        if len(query.split()) < 3:
            return
        t0 = time.time()
        try:
            p = await asyncio.create_subprocess_exec(
                str(SEARCH_PY), str(SEARCH_SCRIPT), "search", query, "--limit", "4", "--json",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(p.communicate(), timeout=8)
            txt = out.decode(errors="ignore")
            hits = json.loads(txt[txt.index("["):]) if "[" in txt else []
        except Exception as e:
            log.info("fast_facts skipped: %s", e)
            return
        facts = []
        for h in hits[:4]:
            snip = re.sub(r"\s+", " ", h.get("snippet", "")).replace(">>>", "").replace("<<<", "")
            facts.append(f"- [{h.get('source')}] {h.get('title', '')}: {snip[:300]}")
        if facts:
            body = fill(self.prompts["fast-facts"], facts="\n".join(facts))
            await self.append("thinking", body[:APPEND_CHAR_CAP], delegation_id)
            log.info("fast facts in %.1fs", time.time() - t0)

    async def ensure_claude(self) -> ClaudeProc:
        if self.claude and self.claude.proc.returncode is None:
            return self.claude
        sysp = fill(self.prompts["claude-system"], channel_id=self.channel_id, thread_ts=self.thread_ts,
                    agent_name=AGENT_NAME)
        # One call = one Slack thread = one fresh Claude session, exactly like a new thread in
        # Slack. (An earlier version resumed one per-caller session across calls; every turn then
        # re-read the whole history and cost roughly fifteen times more.)
        self.claude = await spawn_claude(getattr(self, "resume_session", None), sysp, self.channel_id, self.thread_ts)
        self.rec("claude_spawn", pid=self.claude.proc.pid, resume=getattr(self, "resume_session", None),
                 model=CLAUDE_MODEL, effort=CLAUDE_EFFORT)
        asyncio.create_task(self.claude_reader(self.claude))
        return self.claude

    async def claude_turn(self, delegation_id: str, transcript: str) -> None:
        c = await self.ensure_claude()
        text = fill(self.prompts["claude-turn"], caller_name=self.caller, agent_name=AGENT_NAME,
                    time=datetime.now().strftime("%H:%M"), delegation_id=delegation_id,
                    transcript=transcript)
        msg = {"type": "user", "session_id": "", "parent_tool_use_id": None,
               "message": {"role": "user", "content": text}}
        self.rec("claude_turn", delegation_id=delegation_id, text=text, steering=c.turn_running)
        if c.turn_running:
            log.info("turn running; steering new delegation into it")
            await self.append("thinking", f"Status: {AGENT_NAME} has received the new request and is adjusting.", delegation_id)
        c.turn_running = True
        c.turn_done.clear()
        c.current_delegation = delegation_id
        c.turn_started = time.time()
        c.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await c.proc.stdin.drain()
        c.last_activity = time.time()

    async def claude_reader(self, c: ClaudeProc) -> None:
        try:
            await self._claude_reader(c)
        except Exception as e:
            log.exception("claude reader died: %s", e)
            self.rec("claude_crash", error=str(e)[:500])
            c.turn_running = False
            c.turn_done.set()
            if not self.ended:
                await self.append("instructions",
                                  f"{AGENT_NAME}'s backend hit an error and is restarting. Tell the caller plainly that {AGENT_NAME} dropped for a moment and will pick up the last request again if the caller repeats it. Do not answer substantive questions yourself.",
                                  None)
            try:
                c.proc.kill()
            except Exception:
                pass
            if self.claude is c:
                self.resume_session = c.session_id   # next delegation respawns and resumes this call's session
                self.claude = None

    async def _claude_reader(self, c: ClaudeProc) -> None:
        async for raw in c.proc.stdout:
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            c.last_activity = time.time()
            typ = ev.get("type")
            did = getattr(c, "current_delegation", None)
            if typ == "system" and ev.get("session_id"):
                if ev["session_id"] != c.session_id:
                    self.rec("claude_session", session_id=ev["session_id"])
                c.session_id = ev["session_id"]
            elif typ == "assistant":
                if ev.get("parent_tool_use_id"):
                    continue  # subagent chatter
                for b in ev.get("message", {}).get("content", []):
                    if b.get("type") == "text" and b["text"].strip():
                        # previous block becomes silent progress; newest waits to be spoken
                        if c.pending_text:
                            await self.append("thinking", f"Status from {AGENT_NAME}: {c.pending_text}", did)
                        c.pending_text = b["text"].strip()
                        self.rec("claude_text", delegation_id=did, text=c.pending_text)
                    elif b.get("type") == "tool_use":
                        name = b.get("name", "")
                        self.rec("tool_use", delegation_id=did, name=name, input=json.dumps(b.get("input", {}), ensure_ascii=False)[:800])
                        if name not in ("Skill",):
                            await self.append("thinking", f"Status: {AGENT_NAME} is using {name}.", did)
                        await self.to_browser({"type": "status", "text": f"tool: {name}…"})
            elif typ == "result":
                if ev.get("session_id"):
                    c.session_id = ev["session_id"]
                    save_claude_session(self.user_id, c.session_id, self.thread_ts)
                final = (c.pending_text or ev.get("result") or "").strip()
                c.pending_text = None
                dur = time.time() - getattr(c, 'turn_started', time.time())
                self.rec("turn_done", delegation_id=did, seconds=round(dur, 1), cost=ev.get("total_cost_usd"),
                         num_turns=ev.get("num_turns"), final=final)
                if final:
                    if not self.ended:
                        await self.append("commentary", final, did)
                    self.post(f":studio_microphone: {final}" if not self.ended
                              else f":studio_microphone: (after the call) {final}")
                log.info("turn done in %.1fs cost=$%.3f turns=%s: %s", dur, ev.get("total_cost_usd") or 0,
                         ev.get("num_turns"), final[:120].replace("\n", " "))
                c.turn_running = False
                c.turn_done.set()
                await self.to_browser({"type": "status", "text": "listening"})
        log.info("claude pid=%s exited rc=%s", c.proc.pid, c.proc.returncode)
        self.rec("claude_exit", pid=c.proc.pid, rc=c.proc.returncode)
        c.turn_running = False
        c.turn_done.set()
        if not self.ended:
            await self.append("instructions",
                              f"{AGENT_NAME}'s backend just disconnected. Tell the caller plainly that the connection dropped and that {AGENT_NAME} will pick this up in the Slack thread. Do not answer substantive questions yourself.",
                              None)

    # --- Lifecycle ------------------------------------------------------------
    async def run(self) -> None:
        self.open_thread()
        log.info("call from %s voice=%s dm=%s thread=%s", self.caller, self.voice, self.channel_id, self.thread_ts)
        live_task = asyncio.create_task(self.run_live())
        try:
            while not self.hangup:
                try:
                    async for msg in self.browser:
                        if isinstance(msg, bytes):
                            if self.live is not None:
                                await self.live_send({"type": "session.input_audio.append",
                                                      "audio": base64.b64encode(msg).decode()})
                        else:
                            ev = json.loads(msg)
                            if ev.get("type") == "hangup":
                                self.hangup = True
                                break
                            if ev.get("type") == "mute":
                                await self.live_send({"type": "session.input_audio.mute"})
                            if ev.get("type") == "unmute":
                                await self.live_send({"type": "session.input_audio.unmute"})
                    if not self.hangup:
                        raise websockets.ConnectionClosedOK(None, None)
                except websockets.ConnectionClosed:
                    if self.hangup or self.live is None:
                        break
                    # The page went away without hanging up: screen lock, tab switch, network.
                    # Keep the Live session and Claude warm and wait for the page to come back.
                    self.browser = None
                    self._reattached.clear()
                    PARKED[self.id] = self
                    log.info("call %s parked (page dropped); waiting %ss", self.id, PARK_SECONDS)
                    self.rec("parked", wait=PARK_SECONDS)
                    await self.append("thinking", "Status: the caller's phone screen may have locked; the line is being held.", None)
                    try:
                        await asyncio.wait_for(self._reattached.wait(), PARK_SECONDS)
                    except asyncio.TimeoutError:
                        PARKED.pop(self.id, None)
                        log.info("call %s not reattached; ending", self.id)
                        break
        finally:
            await self.end(live_task)

    async def end(self, live_task: asyncio.Task) -> None:
        if self.ended:
            return
        self.ended = True
        self._commit("caller"); self._commit("agent")
        try:
            await self.live_send({"type": "session.close"})
            await asyncio.wait_for(live_task, 5)
        except Exception:
            live_task.cancel()
        mins = (time.time() - self.started) / 60
        lines = "\n".join(f"*{self.caller if r == 'caller' else AGENT_NAME}:* {t}" for r, t in self.transcript)
        self.post(f":telephone: Call ended after {mins:.1f} min.\n\n*Transcript*\n{lines[:3500] or '_(nothing said)_'}")
        log.info("call ended %.1f min, %d transcript lines", mins, len(self.transcript))
        self.rec("end", minutes=round(mins, 2), lines=len(self.transcript))
        asyncio.create_task(self.reap_claude())

    async def reap_claude(self) -> None:
        c = self.claude
        if not c:
            return
        # Calls end, work doesn't: let a running turn finish and land in the thread.
        while c.proc.returncode is None and (c.turn_running or time.time() - c.last_activity < PROCESS_LINGER):
            await asyncio.sleep(15)
        if c.proc.returncode is None:
            try:
                c.proc.stdin.close()
                await asyncio.wait_for(c.proc.wait(), 15)
            except Exception:
                c.proc.kill()
            log.info("reaped claude pid=%s", c.proc.pid)


# ---------------------------------------------------------------------------
# Server: static page + websocket on one TLS port
# ---------------------------------------------------------------------------

INDEX = (HERE / "static" / "index.html")


def process_request(connection, request):
    path = urlparse(request.path).path
    if path == "/ws":
        return None  # proceed with websocket handshake
    if path == "/favicon.ico":
        return connection.respond(HTTPStatus.NO_CONTENT, "")
    if path == "/health":
        resp = connection.respond(HTTPStatus.OK, json.dumps({"ok": True, "voice": LIVE_VOICE, "voices": VOICES,
                                                            "model": CLAUDE_MODEL, "effort": CLAUDE_EFFORT}))
        resp.headers["Content-Type"] = "application/json"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
    if path in ("/", "/index.html"):
        page = (INDEX.read_text()
                .replace("__AGENT_NAME__", AGENT_NAME)
                .replace("__AGENT_JSON__", json.dumps(AGENT_NAME))
                .replace("__CALLERS_JSON__", json.dumps(USERS)))
        resp = connection.respond(HTTPStatus.OK, page)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp
    return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")


async def handler(ws):
    q = parse_qs(urlparse(ws.request.path).query)
    resume = q.get("resume", [""])[0]
    if resume and resume in PARKED:
        call = PARKED[resume]
        await call.attach(ws)
        await ws.wait_closed()   # the original run() loop reads this socket now; keep the handler alive
        return
    if resume:
        log.info("resume %s requested but not parked; starting a new call", resume)
    ip = (ws.remote_address or ("?",))[0]
    chosen = q.get("user", [""])[0]
    if chosen in USERS:
        user_id, via = chosen, "chosen"
        remember_device(ip, chosen)
    elif device_user(ip) in USERS:
        user_id, via = device_user(ip), "device"
    else:
        user_id, via = DEFAULT_USER, "default"
    log.info("caller %s via %s from %s", USERS.get(user_id), via, ip)
    voice = q.get("voice", [LIVE_VOICE])[0]
    call = Call(ws, user_id, voice)
    call.via = via
    try:
        await call.run()
    except Exception as e:
        log.exception("call crashed: %s", e)
        try:
            await call.end(asyncio.create_task(asyncio.sleep(0)))
        except Exception:
            pass


async def main() -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(HERE / "certs" / "cert.pem", HERE / "certs" / "key.pem")
    async with serve(handler, "0.0.0.0", PORT, ssl=ctx, process_request=process_request,
                     max_size=None, ping_interval=20, ping_timeout=60):
        log.info("voice bridge listening on https://0.0.0.0:%d  (model=%s effort=%s)", PORT, CLAUDE_MODEL, CLAUDE_EFFORT)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
