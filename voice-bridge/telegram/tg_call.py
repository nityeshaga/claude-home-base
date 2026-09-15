"""Telegram front door for the voice bridge.

The assistant's Telegram *user* account (session file: <TG_SESSION>.session, created by
login.py) answers private calls from allow-listed people and relays PCM16 24 kHz mono both
ways to the bridge's /ws endpoint, exactly as the browser page would. The bridge does
everything else (GPT-Live, Claude, Slack thread).

Env: TG_API_ID, TG_API_HASH (from https://my.telegram.org), TG_SESSION (default "voice"),
VOICE_BRIDGE_WS (default wss://127.0.0.1:9443/ws).
"""
import asyncio, json, logging, os, ssl, time
from pathlib import Path

import websockets
from pyrogram import Client
from pytgcalls import PyTgCalls, filters
from pytgcalls.types.raw import AudioParameters
from pytgcalls.types import (ChatUpdate, Device, Direction,
                             ExternalMedia, MediaStream, RecordStream, StreamFrames)

HERE = Path(__file__).parent
log = logging.getLogger("tg")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

API_ID, API_HASH = int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"]
SESSION = os.environ.get("TG_SESSION", "voice")
BRIDGE_WS = os.environ.get("VOICE_BRIDGE_WS", "wss://127.0.0.1:9443/ws")
RATE, CH = 24000, 1
FRAME_MS = 10
FRAME_BYTES = RATE * CH * 2 * FRAME_MS // 1000   # 480 bytes per 10 ms

def allowlist() -> dict:
    """telegram user id (str) -> slack user id. Edit allow.json to add callers."""
    p = HERE / "allow.json"
    return json.loads(p.read_text()) if p.exists() else {}

app = Client(SESSION, api_id=API_ID, api_hash=API_HASH, workdir=str(HERE))
tg = PyTgCalls(app)
LIVE: dict[int, "Relay"] = {}


class Relay:
    def __init__(self, chat_id: int, slack_user: str):
        self.chat_id, self.slack_user = chat_id, slack_user
        self.ws = None
        self.out_q: asyncio.Queue[bytes] = asyncio.Queue()
        self.done = asyncio.Event()
        self.started = time.time()
        self.sent = 0

    async def run(self):
        """Hold the bridge socket for the life of the Telegram call. If it drops while the
        call is still up, reconnect with ?resume=<call id>; the bridge parks a call for 90 s."""
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        self.call_id = None
        self.closed = False
        attempt = 0
        while not self.closed:
            uri = f"{BRIDGE_WS}?user={self.slack_user}&via=telegram"
            if self.call_id:
                uri += f"&resume={self.call_id}"
            try:
                async with websockets.connect(uri, ssl=ctx, max_size=None, ping_interval=20, ping_timeout=60) as ws:
                    self.ws = ws
                    attempt = 0
                    log.info("bridge connected for chat %s (resume=%s)", self.chat_id, self.call_id)
                    sender = asyncio.create_task(self._to_telegram())
                    try:
                        async for msg in ws:
                            if isinstance(msg, bytes):
                                self.recv_bytes = getattr(self, "recv_bytes", 0) + len(msg)
                                if self.recv_bytes // 48000 != (self.recv_bytes - len(msg)) // 48000:
                                    log.info("bridge audio received: %d bytes", self.recv_bytes)
                                self.q_bytes = getattr(self, "q_bytes", 0) + len(msg)
                                await self.out_q.put(msg)
                            else:
                                ev = json.loads(msg)
                                if ev.get("type") == "call":
                                    self.call_id = ev.get("id")
                                if ev.get("type") in ("status", "thread", "call"):
                                    log.info("bridge %s: %s", ev.get("type"), ev.get("text") or ev.get("url") or ev.get("id"))
                    finally:
                        sender.cancel()
                        self.ws = None
                log.info("bridge socket closed for chat %s (closed=%s)", self.chat_id, self.closed)
            except Exception as e:
                log.warning("bridge socket error for chat %s: %s", self.chat_id, e)
            if self.closed:
                break
            attempt += 1
            if attempt > 30:
                log.error("bridge unreachable for chat %s; giving up", self.chat_id); break
            await asyncio.sleep(min(3, 0.5 * attempt))
        self.done.set()

    async def _to_telegram(self):
        """Bridge audio -> Telegram call.
        Rate-limited to real time (never faster than one 10 ms frame per 10 ms), with the
        schedule resetting whenever the source pauses, so a burst after silence is played
        at normal speed. Latency is bounded by dropping *silent* frames only when a real
        backlog (> 200 ms queued) exists."""
        import array
        buf = b""
        next_due = time.monotonic()
        while True:
            chunk = await self.out_q.get()
            self.q_bytes = getattr(self, "q_bytes", 0) - len(chunk)
            buf += chunk
            while len(buf) >= FRAME_BYTES:
                frame, buf = buf[:FRAME_BYTES], buf[FRAME_BYTES:]
                backlog_ms = (getattr(self, "q_bytes", 0) + len(buf)) / FRAME_BYTES * FRAME_MS
                if backlog_ms > 200:
                    a = array.array("h", frame)
                    if max(abs(x) for x in a) < 200:
                        self.dropped = getattr(self, "dropped", 0) + 1
                        continue
                now = time.monotonic()
                if next_due > now:
                    await asyncio.sleep(next_due - now)
                    now = time.monotonic()
                next_due = max(next_due, now - 0.05) + FRAME_MS / 1000
                try:
                    await tg.send_frame(self.chat_id, Device.MICROPHONE, frame)
                except Exception as e:
                    log.warning("send_frame failed: %s", e); return
                self.sent += 1
                if self.sent % 500 == 0:
                    log.info("sent %d frames; backlog %.0f ms; dropped-silence %d",
                             self.sent, backlog_ms, getattr(self, "dropped", 0))

    async def from_telegram(self, data: bytes):
        if self.ws is not None:
            try:
                await self.ws.send(data)
            except Exception:
                pass

    async def hangup(self):
        self.closed = True
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps({"type": "hangup"}))
                await asyncio.sleep(0.5)
                await self.ws.close()
            except Exception:
                pass


@tg.on_update(filters.chat_update(ChatUpdate.Status.INCOMING_CALL))
async def on_incoming(_, u: ChatUpdate):
    who = str(u.chat_id)
    slack_user = allowlist().get(who)
    try:
        user = await app.get_users(u.chat_id)
        label = f"{user.first_name or ''} @{user.username or '-'} ({who})"
    except Exception:
        label = who
    if not slack_user:
        log.warning("incoming call from non-allowlisted %s; declining. Add to allow.json.", label)
        try:
            await app.discard_call(u.chat_id) if hasattr(app, "discard_call") else None
        except Exception:
            pass
        return
    log.info("incoming call from %s -> slack %s; answering", label, slack_user)
    params = AudioParameters(RATE, CH)
    relay = Relay(u.chat_id, slack_user)
    LIVE[u.chat_id] = relay
    task = asyncio.create_task(relay.run())
    try:
        await tg.play(u.chat_id, MediaStream(ExternalMedia.AUDIO, audio_parameters=params))
        await tg.record(u.chat_id, RecordStream(audio=True, audio_parameters=params))
        log.info("call %s connected", u.chat_id)
    except Exception as e:
        log.exception("answer failed: %s", e)
        await relay.hangup(); LIVE.pop(u.chat_id, None); task.cancel()


FRAMES: dict[str, int] = {}
@tg.on_update(filters.stream_frame())
async def on_frames(_, u: StreamFrames):
    key = f"{u.direction}/{u.device}"
    n = FRAMES[key] = FRAMES.get(key, 0) + len(u.frames)
    if n % 100 < len(u.frames):
        log.info("frames %s: %d (last %d bytes)", key, n, len(u.frames[-1].frame) if u.frames else 0)
    relay = LIVE.get(u.chat_id)
    if relay and u.direction & Direction.INCOMING:
        for f in u.frames:
            await relay.from_telegram(f.frame)


@tg.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
async def on_left(_, u: ChatUpdate):
    relay = LIVE.pop(u.chat_id, None)
    if relay:
        log.info("call %s ended after %.1f min", u.chat_id, (time.time() - relay.started) / 60)
        await relay.hangup()


from pyrogram import filters as pf
@app.on_message(pf.private)
async def on_msg(_, m):
    log.info("message from %s @%s (%s): %s", m.from_user.first_name, m.from_user.username, m.from_user.id, (m.text or "")[:80])
    if str(m.from_user.id) not in allowlist():
        await m.reply_text("Got it. Your id has been logged; once it is on the allow-list you can call.")

async def main():
    await tg.start()
    me = await app.get_me()
    log.info("Telegram front door up as %s (%s); allowlist=%s", me.first_name, me.id, allowlist())
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
