# File Explorer

A beautiful, self-contained file browser for your AI employee's machine. Browse files, render markdown, view code with syntax highlighting, and monitor launchd scheduled tasks — all from any browser on your local network.

Dependencies: Flask and Waitress (production WSGI server).

## Quick start

```bash
pip install flask waitress
python3 server.py
# → File Explorer running on port 8888
```

Open `http://<machine-ip>:8888` in your browser.

## Configuration

All settings are via environment variables:

| Variable | Default | Description |
|---|---|---|
| `FILE_EXPLORER_BASE_DIR` | `~` (home dir) | Root directory to browse |
| `FILE_EXPLORER_PORT` | `8888` | Port to listen on |
| `FILE_EXPLORER_NAME` | `Your AI Employee` | Display name shown in the UI |
| `FILE_EXPLORER_TASK_PREFIXES` | _(none)_ | Comma-separated launchd label prefixes to monitor (e.g. `com.myai.,com.cc.`) |
| `FILE_EXPLORER_BOT_DIR` | `~/Projects/slack-bot` | Slack bot directory — where `model-config.json` and the bot `.env` live (for the `/models` page) |
| `FILE_EXPLORER_DM_USERS` | _(none)_ | DM rows on the `/models` page, `U0AAAAAAA:Alice,U0BBBBBBB:Bob` |
| `FILE_EXPLORER_COMMENT_AUTHORS` | _(none)_ | Names in the inline-comment author picker, `Alice,Bob` |
| `FILE_EXPLORER_ASSISTANT_NAME` | `FILE_EXPLORER_NAME` | What to call the assistant in a transcript |
| `FILE_EXPLORER_SLACK_USERS` | _(none)_ | Slack IDs shown as names in transcripts, `U0AAAAAAA:Alice` |
| `FILE_EXPLORER_SLACK_TEAM` | _(none)_ | Slack subdomain, for deep links from a transcript back to its thread |
| `FILE_EXPLORER_SCHEDULED_PHRASES` | _(none)_ | Prompt phrases that mark a session as a scheduled run |
| `FILE_EXPLORER_TRUST_BATTERY_DIR` | `<base>/trust-battery` | One `<name>.json` per person; the home page shows a card for each |

Example with all options:

```bash
FILE_EXPLORER_NAME="Jarvis" \
FILE_EXPLORER_PORT=9000 \
FILE_EXPLORER_TASK_PREFIXES="com.jarvis.,com.cc." \
python3 server.py
```

## Features

- **File browsing** with directory listing, breadcrumbs, and sidebar navigation
- **Markdown rendering** with syntax-highlighted code blocks
- **Models page** (`/models`, supervisors only) — which model and effort answers in each Slack channel and DM, plus an optional per-model prompt. The default row is a dropdown too once `model-config.json` names a `default_model`, so you can move every unconfigured room to another model from the page. Each prompt carries a repeat cadence — session start only, or re-sent with every Nth message. Channels with a setting of their own list first; the rest fold behind a "show all" row. Edits the bot's `model-config.json` (autosaving, validated, backed up to `.model-config-history/`); the bot picks changes up on the next spawn, no restart needed
- **Comments on rendered HTML** — open any `.html` file through `/raw/...`, hit **Comment**, and click an element to pin a note to it, Figma-style. Comments are stored in a `<file>.comments.json` sidecar (the file itself is never touched) and are readable by your AI over the `/comments` endpoint, so "address the comments on this page" is a thing you can ask for
- **Comments on markdown** — select any prose in a rendered `.md` file and leave a note in the margin rail, Google-Docs style. Same `<file>.comments.json` sidecar as the HTML overlay, same `/comments` endpoint, so your AI addresses both the same way. On narrow screens the rail becomes numbered markers and a bottom sheet
- **Trust battery cards** — drop a `<name>.json` into `trust-battery/` and the home page grows a card per person: charge, autonomy tier, a 30-entry sparkline, and the latest delta with its reasoning
- **Code viewing** with language-aware syntax highlighting (40+ extensions)
- **HTML preview** with render/source toggle
- **Markdown editing** directly from the browser (any `.md` file), with edit-conflict protection — if a file changes on disk (e.g. an agent edits it) while you're editing, Save surfaces an inline "Overwrite anyway / Reload file" prompt instead of silently clobbering it. Unsaved changes trigger a leave-page warning.
- **Scheduled task monitoring** — view launchd jobs, their schedules, run history, and Claude Code session output
- **24-hour timeline SVG** showing when tasks run throughout the day
- **14-day reliability strip** tracking task execution history
- **Mobile responsive** with hamburger menu sidebar
- **Diary mode** — files named `YYYY-MM-DD.md` in a `diary/` folder display as human-readable dates

### Navigation & power-user features

- **Cmd+K / Ctrl+K search palette** — fuzzy jump to any file or folder; arrow keys to move, Enter to open, Esc to close
- **Keyboard navigation** — `j`/`k` to move between rows, Enter to open, `h`/Backspace to go up a directory, `g`-chords (`gh` home, `gt` tasks, `gc` conversations, `gd` diary), and `?` for a shortcuts overlay
- **Sortable, filterable listings** — directories with 8+ entries get a type-to-filter box and name/size/modified sort toggles (folders always grouped first); your sort choice is remembered per directory
- **Conversation browser** — reads Claude Code session logs, grouped by date, with source badges (channel / DM / scheduled / terminal) and an All / Conversations / Scheduled filter. Message blocks render by kind: thinking, tool calls with diffs, collapsed skill loads, and tool results. Slack user IDs render as names when `FILE_EXPLORER_SLACK_USERS` maps them
- **Full tool I/O on demand** — every tool call and result carries an expandable pane that fetches the complete pretty-printed payload only when you open it, so a session with hundreds of tool calls stays a small page
- **Subagent transcripts** — an `Agent` tool call links straight through to that subagent's own sidechain transcript
- **Session boot strip** — each transcript opens with the model that served it and its token counts
- **Infinite scroll + live view** — long conversations load older messages as you scroll; a session still being written shows a pulsing "live" indicator and streams new messages in as they arrive
- **Minimap & table-of-contents rails** — on wide screens, a right-hand rail lists the user turns in a conversation (or the headings in a long markdown doc) with scroll-spy highlighting
- **Per-page browser titles** and an amber open-book favicon

### Comments

Two flavours, one sidecar format and one endpoint.

**On markdown** — select text in a rendered `.md` file; a mark appears beside the
selection. Click it, type, and the note parks in the right-hand rail next to what it
points at. Set `FILE_EXPLORER_COMMENT_AUTHORS` to attribute notes to a person.
Comments whose anchor text has since been edited away are shown as "text changed"
rather than dropped.

### Comments on rendered HTML

Open any `.html` file through `/raw/...`, click **Comment** in the corner, then click
the element you want to talk about and type. The note is pinned to that element by
CSS selector and saved in a `<file>.comments.json` sidecar — the HTML on disk is
never modified.

Your AI addresses them over the same endpoint. Worth putting in its `CLAUDE.md`:

```bash
curl -s "http://<host>:8888/comments?path=/abs/file.html"
curl -s -X POST "http://<host>:8888/comments" -H "Content-Type: application/json" \
  -d '{"path":"/abs/file.html","action":"resolve","id":"<id>"}'   # or "delete"
```

## Hero image

Drop a `hero.png` or `hero.jpg` in this directory to show it on the home page. Otherwise, a text greeting is shown.

## Task descriptions

To add human-readable descriptions for your scheduled tasks, edit the `TASK_DESCRIPTIONS` dict in `server.py`:

```python
TASK_DESCRIPTIONS = {
    'com.myai.morning-brief': 'Sends a morning briefing to the team',
    'com.myai.daily-diary': 'Writes an introspective diary entry',
}
```
