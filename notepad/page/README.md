# Notepad page

One page per person over the notepad. Open it, see who is waiting on you, tap once.

Each item has four controls and nothing else:

| Control | Effect |
|---|---|
| The suggested action (one button) | Starts or resumes a Claude session in Slack with that item's instruction |
| "I handled it" | Closes the item as handled |
| The text box | Starts or resumes a session with your own instruction |
| The cross | Closes the item as dismissed |

An item you have seen moves to **Read** on the next load. An item with a session running moves to **In progress**, with a link to its Slack thread.

## Run

Needs Flask and Waitress, and the Slack bot from this repo running on the same machine.

```bash
pip install flask waitress
cp ../config.json.example ../config.json     # list people and their Slack user IDs
python3 server.py                            # http://<this-machine>:8950/<name>
```

| Setting | Default | What it is |
|---|---|---|
| `NOTEPAD_PAGE_PORT` | `8950` | Port to listen on |
| `BOT_ACT_URL` | `http://127.0.0.1:3000/notepad/act` | The bot's entry point. Use localhost, never the tunnel URL: the bot refuses relayed requests. |
| `BOT_SESSIONS_JSON` | `~/Projects/slack-bot/.sessions.json` | The bot's thread-to-session map, read only |
| `NOTEPAD_PAGE_HOSTS` | _(none)_ | Extra hostnames the page may be opened under, comma-separated |
| `NOTEPAD_DB`, `NOTEPAD_CONFIG` | next to `notepad.py` | Same as the command |

In `config.json`: `people.<name>.slack_user_id` says whose DM a tap opens a thread in. `assistant_name` is what the page calls your AI. `slack_workspace` (the subdomain in `<workspace>.slack.com`) turns thread references into links.

To keep it running, give it a launchd job like the bot's, with `WorkingDirectory` set to your home directory.

## Who can reach it

A tap starts a session with that person's full permissions, so the page is strict about who is asking:

- It answers only this machine and Tailscale addresses.
- It answers only under `localhost`, this machine's own name, or a name in `NOTEPAD_PAGE_HOSTS`.
- It refuses a form posted from another site.

There is no login. Anyone on your tailnet can open anyone's page.

## What a tap sends the bot

```
POST http://127.0.0.1:3000/notepad/act
{ "user_id": "U0AAAAAAA", "item_id": 42, "instruction": "...", "anchor_text": "...",
  "thread_ts": null, "channel": null, "session_id": null, "fork": false, "dry_run": false }
-> 200 { "ok": true, "mode": "new" | "resumed", "channel": "D...", "thread_ts": "..." }
```

- No `thread_ts`: the bot opens the person's DM, posts an anchor message, and starts a session in that thread.
- With `thread_ts`: the bot posts the instruction in the thread and resumes its session.
- `session_id` with `fork: true` starts the thread as a copy of that session. Use it when the session belongs to a scheduled job and sits behind several items (`notepad add --session <id> --shared`).
- `dry_run: true` validates and returns without posting.

The route returns at once. It does not wait for the session.

The session is told to run `notepad update <id> --standing "..."` when it stops, and `notepad done <id> --how handled` if the work resolves the item.

## Fonts

The page is set in Familjen Grotesk and Newsreader when they are installed, and falls back to system fonts. No font files ship here and nothing is fetched from the network.
