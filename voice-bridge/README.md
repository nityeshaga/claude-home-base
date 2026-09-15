# Voice bridge — call your AI

A second medium into the same AI that answers you in Slack. Pick up a phone page in a browser (or place a Telegram call) and talk; the AI answers in its own voice, with all its tools, memory and context. Slack stays the desk: every call opens a DM thread where anything visual lands, and replying in that thread after the call continues the same Claude session.

```
you (mic) ──PCM16──▶ bridge.py ──▶ OpenAI GPT-Live-1 (speech in, speech out, client delegation)
                        │                     │
                        │            session.delegation.created
                        │                     ▼
                        │          one user turn ──▶ claude -p (stream-json, one process per call)
                        │                     │
                        │        thinking / commentary appends ◀── text blocks / final answer
                        ▼
              Slack DM thread (transcript, artifacts; reply = resume this session)
```

## How it works

**GPT-Live-1 does the talking.** OpenAI's live voice model handles turn-taking, transcription and speech. It runs in *client delegation* mode: it is told it is only the mouth and ears, and that anything of substance must be delegated to a backend. When it decides to delegate it emits `session.delegation.created` (id and offset only, no text).

**A delegation is a Slack message.** The bridge mirrors the session layer of `bot.py` exactly. Where the Slack bot turns one incoming message into one user turn on a long-lived `claude -p` process, the bridge turns one delegation into one user turn: it slices the transcript since the last turn, formats it with the `## claude-turn` prompt, and writes it to Claude's stdin. If a turn is already running, the new delegation is written anyway and the CLI steers the running turn at its next tool boundary. That is how "Thursday… no, Friday" works without an undo.

**One call = one thread = one fresh Claude session.** At pick-up the bridge opens a DM thread with the caller and spawns a fresh Claude process for the call, the same as a new thread in Slack. Claude's session id is registered in the Slack bot's `.sessions.json` under the thread's `ts`, so a reply in that thread later resumes the call's session. (An earlier version resumed one session per caller across calls; every turn re-read the whole history and cost about fifteen times more.)

**Two channels back to the voice.** Claude's intermediate text blocks and tool names go back as `session.thinking.append` (silent context, prefixed `Status:` so the voice model never reads them aloud as an answer). The final text block goes back as `session.commentary.append` and is spoken. The final text is also posted to the thread.

**Calls end, work doesn't.** On hang-up the bridge closes the Live session, posts the transcript to the thread, and leaves Claude running for up to ten minutes (or until its turn ends) so long work still lands in the thread.

| Slack bot | Voice bridge |
|---|---|
| One Claude process per thread | One fresh process and session per call |
| Slack message arrives | `session.delegation.created` arrives |
| Text + sender prefix | Transcript slice since last turn + call preamble |
| Idle: stdin write, wait | Same |
| Turn running: stdin write, CLI steers | Same |
| Text blocks → thread | Final → `commentary` (spoken); intermediate → `thinking` (silent) |

## Files

| File | What it is |
|---|---|
| `bridge.py` | The whole server: TLS websocket on one port, the static page, the Live relay, the Claude process, the Slack thread. |
| `prompts.md` | Every prompt, one `## name` section each, parsed at call start. Edit freely; no restart. |
| `static/index.html` | The phone: one lamp that is the pick-up button and breathes with the AI's voice, a thin ring for your mic, the transcript as a script, caller chips, timer, thread link. Mic → PCM16 24 kHz → websocket; PCM16 back → speaker. |
| `callers.json` | Slack user id → first name for everyone allowed to call. Copy from `callers.json.example`. |
| `telegram/` | Optional front door: a Telegram user account answers calls and relays audio to the bridge. See below. |
| `tests/fake_caller.py` | Streams `say`-synthesised sentences into the bridge like a browser would and prints every event. Use it before asking a human to test. |
| `launchd/` | Example plists and wrapper scripts to run both services as always-on launchd agents. |
| `.env.example` | Every environment knob. |

Runtime files the bridge creates (all git-ignored): `state.json` (learned device → caller map), `logs/`, `calls/<thread_ts>.jsonl` (the full record of one call: every transcript line, delegation, append, tool call and text block, so intermediate backend output is reviewable without posting it to the thread).

## Setup

Needs the Slack bot from this repo running (the bridge reads `SLACK_BOT_TOKEN` from its `.env` and writes to its `.sessions.json`), the Claude Code CLI, an OpenAI API key with access to `gpt-live-1`, and Python 3.11+.

```bash
cd voice-bridge
python3 -m venv venv && venv/bin/pip install -r requirements.txt

cp .env.example .env            # OPENAI_API_KEY, SLACK_BOT_DIR, VOICE_AGENT_NAME, ...
cp callers.json.example callers.json   # Slack user ids → names

# Browsers refuse mic access over plain HTTP, so the bridge serves TLS with a self-signed cert.
# Accept it once per device.
mkdir certs && openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout certs/key.pem -out certs/cert.pem -subj "/CN=$(hostname)"

venv/bin/python bridge.py
# open https://<your-mac>:9443   (add ?user=<slack id> to say who is calling)
```

Then tell your AI it can be on a call. Add something like this to its `CLAUDE.md`:

> `VOICE_CALL=1` in your env means you are on a live voice call. Write for the ear, post anything visual to the Slack thread in `CLAUDE_CHANNEL_ID` / `CLAUDE_THREAD_TS`, and get a spoken yes before any outward action.

The bridge sets `VOICE_CALL`, `CLAUDE_CHANNEL_ID`, `CLAUDE_THREAD_TS` and `CLAUDE_SESSION_ID` on the Claude process, the same variables `bot.py` sets.

### Running it as a service

`launchd/` has a plist and wrapper for each service. Copy the wrapper to `~/scripts/`, set `BRIDGE_DIR` in it, replace `YOUR_USERNAME` in the plist, copy the plist to `~/Library/LaunchAgents/`, `launchctl load` it. Both are `KeepAlive` servers, not cron jobs; the rules in [`../jobs/README.md`](../jobs/README.md) about `WorkingDirectory` and local times still apply. Restart after a code change with `launchctl kickstart -k gui/$(id -u)/com.claude.voice-bridge`. Prompt edits need no restart.

### Endpoints

- `/` the phone. `/ws?user=<slack id>&voice=<name>` the call socket. `/health` JSON with CORS.
- Who is calling, in order: `?user=` (the page's chips, remembered in localStorage; picking a name also teaches the bridge that this source address belongs to that person), then the learned address map, then the first entry in `callers.json` (or `VOICE_DEFAULT_USER`). The page header shows "for alice · this device" so a wrong guess is visible before you speak.

### Surviving the lock screen

Two layers. The page takes a Screen Wake Lock while live and re-acquires it on `visibilitychange`, so the phone stops locking mid-call (needs https, which you have). If the page still drops (lock anyway, app switch, network blip), the bridge does not end the call: it parks it for `PARK_SECONDS` (90) with the Live session and Claude untouched, tells the voice model the line is being held, and the page reconnects with `?resume=<call id>`, swaps the socket and replays the transcript. Audio during the gap is lost on both sides; that is the limit of a browser tab, and the reason the Telegram front door exists.

## Telegram front door

iOS suspends web pages on lock. Telegram calls are CallKit calls, so the lock screen, AirPods and CarPlay all work with no app of your own. `telegram/tg_call.py` signs in as a Telegram **user** account, answers private calls from ids in `telegram/allow.json` (Telegram id → Slack id), and relays PCM16 24 kHz mono to the bridge's `/ws` exactly like the page does. Everything downstream is unchanged. Unknown callers are declined and logged; a private message to the account logs the sender's id so you can allow-list it.

**Caveat, read this first.** This is an *automated user account*, not a bot: Telegram's Bot API cannot receive voice calls, so the adapter drives a normal account through the MTProto client library (Kurigram, a Pyrogram fork) plus pytgcalls/ntgcalls. Automating user accounts sits outside what Telegram officially supports and accounts doing it can be limited or banned. Use a dedicated phone number for the assistant, not your own, get your own `api_id`/`api_hash` from [my.telegram.org](https://my.telegram.org), and treat the `.session` file as a credential.

```bash
cd voice-bridge/telegram
python3 -m venv venv && venv/bin/pip install -r requirements.txt   # separate venv: different websockets pin
cp allow.json.example allow.json
# put TG_API_ID, TG_API_HASH in ../.env, then sign in once (interactive: login code, 2FA password)
set -a; source ../.env; set +a
TG_PHONE=+1... venv/bin/python login.py
venv/bin/python tg_call.py
```

Things that cost real debugging time, so you don't have to: incoming audio arrives as `Direction.INCOMING / Device.MICROPHONE`, not `SPEAKER`. Outgoing frames must be rate-limited to real time, with the schedule resetting whenever the source pauses (a fixed-from-start schedule made speech fast and hazy). Backlog is trimmed by dropping *silent* frames only, and only when more than 200 ms is queued. If the bridge socket drops mid-call the adapter reconnects with `?resume=`.

## How a turn flows

1. Live streams transcripts of both sides; the bridge keeps them.
2. Live emits `session.delegation.created`. The bridge slices the transcript since the last turn and sends one user turn to Claude, formatted by `## claude-turn`.
3. Optionally (`VOICE_FAST_FACTS=1`) the search CLI in `../search/` runs on the last utterance and hits go back as a `thinking` append within about two seconds.
4. Claude's intermediate text and tool names go back as `thinking`; the final text goes back as `commentary` and is posted to the thread.
5. A delegation that arrives mid-turn is written to stdin anyway; the CLI steers the running turn.
6. Hang-up: Live closes, the transcript is posted, Claude lingers ten minutes so long work still lands.

Measured with a synthetic caller (Opus, low effort):

| Step | Time |
|---|---|
| Delegation → first Claude turn, including cold spawn | 11.5 s |
| Delegation → spoken answer, warm session | 3.6 s |
| Voice model's own turn-taking | ~1 s |

## Rails

- **Confirmation gate** lives in `## claude-system`: no outward action (email, posting outside the call thread, booking, paying, deleting) without a spoken yes. Speech is mis-transcribed more often than text is mistyped.
- **Silent appends are never answers.** The first real failure: the voice model turned a fast-facts append into a confident wrong answer before Claude replied. Every silent append is now prefixed `Status:` or `Background`, `## live-instructions` says those are never answers, and fast facts are off by default.
- **Append cap**: about 500 tokens per append; the bridge chunks at 1800 characters.
- The voice model answering as the AI without delegating is the expected first failure. Fix it in `## live-instructions`, not in code.
- Claude's stream-json lines can carry a whole image (a `Read` on a PNG), so the subprocess reader has a 256 MB line limit; if the reader still crashes, Claude is respawned resuming the same session instead of silently going dead.

## Testing without a human

```bash
venv/bin/python tests/fake_caller.py "What did we talk about today?" "And what is on the calendar tomorrow?"
```

Each sentence is synthesised with macOS `say`, converted to PCM16 24 kHz, streamed in 100 ms chunks, then the script sends silence for `WAIT` seconds (default 45) so the model can take its turn. Every transcript line and status event is printed. For the page itself, drive a real browser against `https://127.0.0.1:9443` with `navigator.mediaDevices.getUserMedia` overridden to return a `MediaStreamDestination` playing a synthesised WAV.

## Cost

The voice layer is billed per second (about $0.05 per minute at the time of writing). The backend cost is your Claude tokens, which is why each call gets a fresh session rather than resuming a growing one.
