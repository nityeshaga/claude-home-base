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
- **Conversation browser** — reads Claude Code session logs, grouped by date, with source badges (channel / DM / scheduled / terminal) and an All / Conversations / Scheduled filter
- **Infinite scroll + live view** — long conversations load older messages as you scroll; a session still being written shows a pulsing "live" indicator and streams new messages in as they arrive
- **Minimap & table-of-contents rails** — on wide screens, a right-hand rail lists the user turns in a conversation (or the headings in a long markdown doc) with scroll-spy highlighting
- **Per-page browser titles** and an amber open-book favicon

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
