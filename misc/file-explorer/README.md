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
- **CLAUDE.md editing** directly from the browser
- **Scheduled task monitoring** — view launchd jobs, their schedules, run history, and Claude Code session output
- **24-hour timeline SVG** showing when tasks run throughout the day
- **14-day reliability strip** tracking task execution history
- **Mobile responsive** with hamburger menu sidebar
- **Diary mode** — files named `YYYY-MM-DD.md` in a `diary/` folder display as human-readable dates

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
