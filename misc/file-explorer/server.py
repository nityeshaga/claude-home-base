#!/usr/bin/env python3
"""
AI Employee File Explorer — browse your AI employee's machine from any browser on the local network.

Configuration via environment variables:
  FILE_EXPLORER_BASE_DIR   — root directory to browse (default: user's home directory)
  FILE_EXPLORER_PORT       — port to listen on (default: 8888)
  FILE_EXPLORER_NAME       — display name for your AI employee (default: "Your AI Employee")
  FILE_EXPLORER_TASK_PREFIXES — comma-separated launchd label prefixes to monitor (default: none)

Flask + Waitress edition: threaded, production-grade, handles broken pipes gracefully.
"""

import os
import json
import hashlib
import html as html_mod
import shutil
import mimetypes
import urllib.parse
import plistlib
import subprocess
import re
import difflib
import threading
import tempfile
import time
import uuid
from collections import OrderedDict
from flask import Flask, Response, redirect, request, jsonify
from pathlib import Path
from datetime import datetime, timedelta

app = Flask(__name__)

BASE_DIR = Path(os.environ.get("FILE_EXPLORER_BASE_DIR", str(Path.home())))
PORT = int(os.environ.get("FILE_EXPLORER_PORT", "8888"))
DISPLAY_NAME = os.environ.get("FILE_EXPLORER_NAME", "Your AI Employee")

# All .md files are editable via the browser UI

# ============================================================
# TAILSCALE IDENTITY — maps Tailscale IPs to team members
# ============================================================
# Each team member's Tailscale IP is mapped to their name and access ring.
# Rings follow teammates-access.md: 1 = supervisor, 2 = core team, 3 = wider team.
#
# HOW TO UPDATE: If a new device joins the tailnet or someone complains they're
# seeing the "unknown visitor" view, ask them to run `tailscale ip -4` on their
# machine and add the IP here. On macOS App Store Tailscale, the IP is visible
# in the Tailscale menu bar icon under "This machine."
TAILSCALE_USERS = {
    "100.123.10.100": {"name": "Claudie", "ring": 0},   # this machine (self)
    "100.71.120.89":  {"name": "Nityesh", "ring": 1},
    # Add more team members here as they connect:
    # "100.x.x.x": {"name": "Natalia", "ring": 1},
    # "100.x.x.x": {"name": "Mike", "ring": 2},
    # "100.x.x.x": {"name": "Brooker", "ring": 2},
}

# Paths restricted by ring. Ring N can see everything rings > N cannot.
# Ring 1 (supervisors): full access
# Ring 2 (core team): no memory, no session logs, no config
# Ring 3+ / unknown: no memory, no logs, no config, no client data, no consulting ops
_MEMORY_DIR = str(BASE_DIR / ".claude" / "projects" / f"-{str(BASE_DIR).replace('/', '-').lstrip('-')}" / "memory")

# Directories hidden from ring 2+
RING2_HIDDEN_PATHS = {
    _MEMORY_DIR,
    str(BASE_DIR / ".claude"),
}

# Directories hidden from ring 3+ / unknown (in addition to ring 2 restrictions)
RING3_HIDDEN_PATHS = RING2_HIDDEN_PATHS | {
    str(BASE_DIR / "Projects" / "slack-bot"),
    str(BASE_DIR / "teammates"),
}


def get_visitor():
    """Identify the connecting visitor by their Tailscale IP.
    Returns dict with 'name' and 'ring', or a default for unknown visitors."""
    ip = request.remote_addr
    user = TAILSCALE_USERS.get(ip)
    if user:
        return user
    # Unknown Tailscale IP — treat as ring 99 (most restricted)
    return {"name": "Visitor", "ring": 99}


def is_path_allowed(path_str, ring):
    """Check if a resolved path is accessible for the given ring."""
    if ring <= 1:
        return True  # supervisors see everything
    resolved = str(Path(path_str).resolve())
    hidden = RING2_HIDDEN_PATHS if ring <= 2 else RING3_HIDDEN_PATHS
    for restricted in hidden:
        if resolved == restricted or resolved.startswith(restricted + "/"):
            return False
    return True


def get_bookmarks_for_ring(ring):
    """Return the bookmark list filtered for the visitor's access ring."""
    all_bookmarks = [
        ("Home", str(BASE_DIR)),
        ("Projects", str(BASE_DIR / "projects")),
        ("Work", str(BASE_DIR / "work")),
        ("Diary", str(BASE_DIR / "diary")),
        ("Bookmarks", str(BASE_DIR / "bookmarks")),
        ("Discoveries", str(BASE_DIR / "discoveries")),
        ("Memory", _MEMORY_DIR),
    ]
    return [(name, path) for name, path in all_bookmarks if is_path_allowed(path, ring)]


# Default bookmarks for backward compat (used nowhere now, kept for reference)
BOOKMARKS = [
    ("Home", str(BASE_DIR)),
    ("Projects", str(BASE_DIR / "projects")),
    ("Work", str(BASE_DIR / "work")),
    ("Diary", str(BASE_DIR / "diary")),
    ("Bookmarks", str(BASE_DIR / "bookmarks")),
    ("Discoveries", str(BASE_DIR / "discoveries")),
    ("Memory", str(BASE_DIR / ".claude" / "projects" / f"-{str(BASE_DIR).replace('/', '-').lstrip('-')}" / "memory")),
]

# Task prefixes from env var
_raw_prefixes = os.environ.get("FILE_EXPLORER_TASK_PREFIXES", "")
TASK_PREFIXES = tuple(p.strip() for p in _raw_prefixes.split(",") if p.strip()) if _raw_prefixes else ()

# Empty task descriptions dict (users populate this)
TASK_DESCRIPTIONS = {}

# Slack bot directory — where the bot's model-config.json and .env live.
# The /models page edits that config (which model answers in which Slack room).
BOT_DIR = Path(os.environ.get("FILE_EXPLORER_BOT_DIR", str(BASE_DIR / "Projects" / "slack-bot")))

# DM rows on the /models page: "U0AAAAAAA:Alice,U0BBBBBBB:Bob".
# Users already named in the config file show up too.
MODELS_DM_USERS = [
    {"id": pair.split(":", 1)[0].strip(), "name": pair.split(":", 1)[1].strip()}
    for pair in os.environ.get("FILE_EXPLORER_DM_USERS", "").split(",")
    if ":" in pair
]

# File extensions to render as text
TEXT_EXTENSIONS = {
    '.md', '.txt', '.py', '.rb', '.js', '.ts', '.jsx', '.tsx', '.json',
    '.yml', '.yaml', '.toml', '.sh', '.bash', '.zsh', '.css', '.html',
    '.erb', '.slim', '.haml', '.sql', '.rake', '.gemspec', '.lock',
    '.cfg', '.ini', '.conf', '.env', '.gitignore', '.dockerignore',
    '.csv', '.xml', '.svg', '.rs', '.go', '.java', '.c', '.h', '.cpp',
    '.hpp', '.swift', '.kt', '.lua', '.r', '.jl', '.ex', '.exs',
    '.log', '.diff', '.patch', '',
}

# Directories to skip
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.bundle', 'vendor', 'tmp', 'log'}

# ============================================================
# SVG ASSETS — Hand-drawn style icons for the study aesthetic
# ============================================================

SIDEBAR_ICONS = {
    "Home": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 18V8.5L10 3l6.5 5.5V18"/><path d="M7.5 18v-5.5c0-.3.2-.5.5-.5h4c.3 0 .5.2.5.5V18"/></svg>',
    "Diary": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 2.5h9.5c.6 0 1 .4 1 1v13c0 .6-.4 1-1 1H5"/><path d="M5 2.5v15"/><path d="M7 2.5v15"/><path d="M11 2.5v7l-1.2-1.5L8.5 10"/></svg>',
    "Discoveries": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="7.5"/><path d="M7 13l1.5-4.5L13 7l-1.5 4.5z"/><circle cx="10" cy="10" r=".8" fill="currentColor"/></svg>',
    "Bookmarks": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2.5h8v14.5l-4-2.8-4 2.8z"/><path d="M6 6.5h8"/></svg>',
    "Projects": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2.5v4"/><circle cx="10" cy="3.5" r="1" fill="currentColor"/><path d="M10 6.5L5.5 17.5"/><path d="M10 6.5l4.5 11"/><path d="M7 13h6"/></svg>',
    "Work": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6V4.5c0-.6.4-1 1-1h4l2 2h7c.6 0 1 .4 1 1V15c0 .6-.4 1-1 1h-14c-.6 0-1-.4-1-1V6z"/><path d="M2.5 8h15"/></svg>',
    "Memory": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="2.5"/><circle cx="4" cy="5" r="1.2"/><circle cx="16" cy="4.5" r="1.2"/><circle cx="15" cy="15.5" r="1.2"/><circle cx="5" cy="16" r="1.2"/><path d="M7.8 8.2L5 5.8"/><path d="M12.2 8.2l3-3"/><path d="M12 11.8l2.2 3"/><path d="M8 11.8l-2.2 3.4"/></svg>',
    "CLAUDE.md": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 2.5h7l3.5 3.5V17c0 .3-.2.5-.5.5H5c-.3 0-.5-.2-.5-.5V3c0-.3.2-.5.5-.5z"/><path d="M12 2.5v3.5h3.5"/><path d="M7.5 9h5"/><path d="M7.5 11.5h5"/><path d="M7.5 14h3"/></svg>',
    "Scheduled Tasks": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="10" cy="10" r="7.5"/><path d="M10 5v5l3.5 2"/><circle cx="10" cy="10" r=".7" fill="currentColor"/><path d="M10 3v.8"/><path d="M17 10h-.8"/><path d="M10 17v-.8"/><path d="M3 10h.8"/></svg>',
    "Conversations": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4.5c-1 0-1.5.5-1.5 1.5v7c0 1 .5 1.5 1.5 1.5h1v2.5l3-2.5h5c1 0 1.5-.5 1.5-1.5V6c0-1-.5-1.5-1.5-1.5z"/><path d="M7 3h9c1 0 1.5.5 1.5 1.5v6c0 1-.5 1.5-1.5 1.5h-.5"/><path d="M6 8h5.5"/><path d="M6 10.5h3.5"/></svg>',
    "Models": '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8.5v7c0 .6.4 1 1 1h9.5c.6 0 1-.4 1-1v-7"/><path d="M6 6.2l4-2.7 4 2.7"/><path d="M6 11.5l4 2.7 4-2.7"/><path d="M6 8.8l4 2.7 4-2.7"/></svg>',
}

FILE_TYPE_SVGS = {
    'md': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 13.5l2-2"/><path d="M4.5 11.5C6 10 9 7 11 4.5c1.5-2 2.5-3 3-3.2-.5.8-1 2-2.5 4.5-1.5 2.5-4 5.5-5.5 6.5l-1.5.7z"/><path d="M9.5 6c.5.3 1 .7 1.2 1"/></svg>',
    'py': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="2.5"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/></svg>',
    'rb': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6l5 8 5-8-2.5-4h-5z"/><path d="M3 6h10"/><path d="M5.5 2L8 6l2.5-4"/><path d="M5.5 6l2.5 8 2.5-8"/></svg>',
    'js': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5H5.5c-1.1 0-2 .9-2 2v0"/><path d="M3.5 4.5v7c0 1.1.9 2 2 2h7"/><path d="M12.5 13.5c1.1 0 2-.9 2-2v-7c0-1.1-.9-2-2-2h0"/><path d="M12.5 4.5v7c0 1.1.4 2 1.5 2"/><path d="M6 6.5h4"/><path d="M6 9h3"/></svg>',
    'ts': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5H5.5c-1.1 0-2 .9-2 2v0"/><path d="M3.5 4.5v7c0 1.1.9 2 2 2h7"/><path d="M12.5 13.5c1.1 0 2-.9 2-2v-7c0-1.1-.9-2-2-2h0"/><path d="M12.5 4.5v7c0 1.1.4 2 1.5 2"/><path d="M6 6.5h4"/><path d="M6 9h3"/></svg>',
    'jsx': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5H5.5c-1.1 0-2 .9-2 2v0"/><path d="M3.5 4.5v7c0 1.1.9 2 2 2h7"/><path d="M12.5 13.5c1.1 0 2-.9 2-2v-7c0-1.1-.9-2-2-2h0"/><path d="M12.5 4.5v7c0 1.1.4 2 1.5 2"/><path d="M6 6.5h4"/><path d="M6 9h3"/></svg>',
    'tsx': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.5H5.5c-1.1 0-2 .9-2 2v0"/><path d="M3.5 4.5v7c0 1.1.9 2 2 2h7"/><path d="M12.5 13.5c1.1 0 2-.9 2-2v-7c0-1.1-.9-2-2-2h0"/><path d="M12.5 4.5v7c0 1.1.4 2 1.5 2"/><path d="M6 6.5h4"/><path d="M6 9h3"/></svg>',
    'sh': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M4.5 6l2.5 2-2.5 2"/><path d="M8.5 10.5h3"/></svg>',
    'bash': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M4.5 6l2.5 2-2.5 2"/><path d="M8.5 10.5h3"/></svg>',
    'zsh': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M4.5 6l2.5 2-2.5 2"/><path d="M8.5 10.5h3"/></svg>',
    'log': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2c-1.1 0-2 .6-2 1.5S3 5 4 5h8.5"/><path d="M4 5v8.5c0 .8.7 1.5 1.5 1.5H13c.6 0 1-.4 1-1V3.5c0-.6-.4-1-1-1h-1"/><path d="M6.5 8h5"/><path d="M6.5 10.5h3.5"/></svg>',
    'json': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="5.5" cy="6.5" r="3"/><path d="M8 8.5l5.5 5.5"/><path d="M11 11.5l1.5-1.5"/><path d="M9.5 10l1.5-1.5"/></svg>',
    'toml': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="5.5" cy="6.5" r="3"/><path d="M8 8.5l5.5 5.5"/><path d="M11 11.5l1.5-1.5"/><path d="M9.5 10l1.5-1.5"/></svg>',
    'yml': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4h4m3 0h5"/><circle cx="8" cy="4" r="1.3"/><path d="M2 8h7m3 0h2"/><circle cx="11" cy="8" r="1.3"/><path d="M2 12h2m3 0h7"/><circle cx="5.5" cy="12" r="1.3"/></svg>',
    'yaml': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4h4m3 0h5"/><circle cx="8" cy="4" r="1.3"/><path d="M2 8h7m3 0h2"/><circle cx="11" cy="8" r="1.3"/><path d="M2 12h2m3 0h7"/><circle cx="5.5" cy="12" r="1.3"/></svg>',
    'html': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3.5L1.5 8 5 12.5"/><path d="M11 3.5l3.5 4.5-3.5 4.5"/><path d="M9.5 2.5l-3 11"/></svg>',
    'erb': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3.5L1.5 8 5 12.5"/><path d="M11 3.5l3.5 4.5-3.5 4.5"/><path d="M9.5 2.5l-3 11"/></svg>',
    'css': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.5 1.5l-5 6.5"/><path d="M7.5 8c-1 0-2.5.5-3 2-.5 1.5 0 2.5.5 3.5.8-.5 2-1.5 2-3 2.5.5 4-.5 4-2 0-1-.5-1.5-1.5-1.5"/></svg>',
    'sql': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="8" cy="4" rx="5.5" ry="2.5"/><path d="M2.5 4v8c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V4"/><path d="M2.5 8c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5"/></svg>',
    '_folder': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2v12"/><path d="M4 2h7.5c.6 0 1 .4 1 1v10c0 .6-.4 1-1 1H4"/><path d="M6 2v12"/><path d="M8 5.5h3"/></svg>',
    '_default': '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 1.5h5.5l3 3V14c0 .3-.2.5-.5.5H4c-.3 0-.5-.2-.5-.5V2c0-.3.2-.5.5-.5z"/><path d="M9.5 1.5v3h3"/><path d="M6 7.5h4"/><path d="M6 10h2.5"/></svg>',
}


# ============================================================
# HELPER FUNCTIONS (unchanged from original)
# ============================================================

def _strip_label_prefixes(label):
    """Remove configured task prefixes from a label for display."""
    for prefix in TASK_PREFIXES:
        if label.startswith(prefix):
            return label[len(prefix):]
    return label


def get_launchd_jobs():
    """Parse all relevant launchd plist files and return job info."""
    jobs = []
    if not TASK_PREFIXES:
        return jobs
    plist_dir = Path.home() / 'Library' / 'LaunchAgents'
    if not plist_dir.exists():
        return jobs

    for plist_file in sorted(plist_dir.iterdir()):
        if not plist_file.suffix == '.plist':
            continue
        if not any(plist_file.name.startswith(p) for p in TASK_PREFIXES):
            continue
        try:
            with open(plist_file, 'rb') as f:
                plist = plistlib.load(f)
        except Exception:
            continue

        label = plist.get('Label', plist_file.stem)
        schedule = _parse_schedule(plist)
        stdout_log = plist.get('StandardOutPath', '')
        stderr_log = plist.get('StandardErrorPath', '')
        script = ''
        args = plist.get('ProgramArguments', [])
        if len(args) >= 2:
            script = args[-1]  # last arg is usually the script

        # Check if running
        is_running = False
        is_loaded = False
        try:
            result = subprocess.run(['launchctl', 'list'], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if label in line:
                    is_loaded = True
                    parts = line.split('\t')
                    if parts[0] != '-' and parts[0] != '0':
                        is_running = True
                    elif parts[0] != '-':
                        is_running = False
                    else:
                        is_running = False
                    # PID present means running
                    if parts[0].isdigit() and int(parts[0]) > 0:
                        is_running = True
                    break
        except Exception:
            pass

        # Last run time from log file
        last_run = None
        log_path = stdout_log or stderr_log
        if log_path and Path(log_path).exists():
            try:
                last_run = datetime.fromtimestamp(Path(log_path).stat().st_mtime)
            except Exception:
                pass

        keep_alive = plist.get('KeepAlive', False)

        jobs.append({
            'label': label,
            'description': TASK_DESCRIPTIONS.get(label, ''),
            'schedule': schedule,
            'script': script,
            'stdout_log': stdout_log,
            'stderr_log': stderr_log,
            'is_running': is_running,
            'is_loaded': is_loaded,
            'keep_alive': keep_alive,
            'last_run': last_run,
            'plist_path': str(plist_file),
        })

    return jobs


def _parse_schedule(plist):
    """Parse StartCalendarInterval or StartInterval into a human-readable string."""
    if 'StartInterval' in plist:
        secs = plist['StartInterval']
        if secs < 60:
            return f'Every {secs}s'
        elif secs < 3600:
            return f'Every {secs // 60}m'
        else:
            return f'Every {secs // 3600}h'

    if 'StartCalendarInterval' in plist:
        cal = plist['StartCalendarInterval']
        if isinstance(cal, dict):
            cal = [cal]
        return _describe_calendar_intervals(cal)

    if plist.get('KeepAlive') or plist.get('RunAtLoad'):
        return 'Always running'

    return 'Manual'


def _describe_calendar_intervals(intervals):
    """Turn calendar intervals into human-readable schedule."""
    days_map = {0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat'}

    if len(intervals) == 1:
        i = intervals[0]
        day = days_map.get(i.get('Weekday'), '')
        hour = i.get('Hour', 0)
        minute = i.get('Minute', 0)
        time_str = f'{hour:02d}:{minute:02d}'
        if day:
            return f'{day} at {time_str}'
        return f'Daily at {time_str}'

    # Check if all same time, different days
    times = set()
    days = []
    for i in intervals:
        h = i.get('Hour', 0)
        m = i.get('Minute', 0)
        times.add((h, m))
        if 'Weekday' in i:
            days.append(i['Weekday'])

    if len(times) == 1:
        h, m = times.pop()
        day_names = [days_map[d] for d in sorted(set(days))]
        return f'{", ".join(day_names)} at {h:02d}:{m:02d}'

    # Multiple times per day
    if days:
        unique_days = sorted(set(days))
        day_names = [days_map[d] for d in unique_days]
        time_strs = sorted(set(f'{h:02d}:{m:02d}' for h, m in times))
        return f'{", ".join(day_names)} at {", ".join(time_strs)}'

    time_strs = sorted(set(f'{h:02d}:{m:02d}' for h, m in times))
    return f'Daily at {", ".join(time_strs)}'


def get_log_runs(log_path, max_entries=50):
    """Parse a log file and extract individual run entries with timestamps."""
    p = Path(log_path)
    if not p.exists():
        return []

    try:
        text = p.read_text(errors='replace')
    except Exception:
        return []

    if not text.strip():
        return [{'time': datetime.fromtimestamp(p.stat().st_mtime).strftime('%b %d, %Y %H:%M'),
                 'content': '(log file exists but is empty)'}]

    lines = text.strip().splitlines()[-max_entries:]
    return [{'content': line} for line in lines]


def extract_claude_prompt(script_path):
    """Extract the -p prompt from a claude invocation in a shell script."""
    p = Path(script_path)
    if not p.exists():
        return None
    try:
        text = p.read_text()
    except Exception:
        return None
    # Join backslash-continued lines
    text = text.replace('\\\n', ' ')
    # Match -p [optional flags] "..." (double quotes)
    match = re.search(r'-p\s+(?:--[\w-]+\s+)*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if match:
        return match.group(1)
    # Match -p [optional flags] '...' (single quotes)
    match = re.search(r"-p\s+(?:--[\w-]+\s+)*'([^']*)'", text, re.DOTALL)
    if match:
        return match.group(1)
    return None


def _get_session_dirs():
    """Return all Claude Code session directories to search."""
    base = Path.home() / '.claude' / 'projects'
    dirs = []
    for d in base.iterdir() if base.exists() else []:
        if d.is_dir() and any(d.glob('*.jsonl')):
            dirs.append(d)
    return dirs


def get_run_history(prompt, days=14, with_output=False):
    """Find recent Claude Code sessions matching a task's prompt.
    If with_output=True, also extract the last substantial assistant text from each session."""
    if not prompt:
        return []
    # Build a search key from the first stable text before any bash variable.
    # Important: JSONL stores newlines as \n so our key must be a single line.
    first_chunk = re.split(r'\$\{?\w+\}?', prompt)[0].strip()
    # Take first line only (newlines won't match JSONL-escaped content)
    first_line = first_chunk.split('\n')[0].strip()
    if len(first_line) >= 15:
        search_keys = [first_line[:50]]
    else:
        # Fallback: strip variables and take first line
        fingerprint = re.sub(r'\$\{?\w+\}?', '', prompt).strip()
        first_line = fingerprint.split('\n')[0].strip()
        if len(first_line) < 15:
            return []
        search_keys = [first_line[:50]]

    cutoff = datetime.now().timestamp() - (days * 86400)
    runs = []

    for sessions_dir in _get_session_dirs():
        for jsonl_file in sorted(sessions_dir.glob('*.jsonl'), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                mtime = jsonl_file.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                break
            try:
                with open(jsonl_file) as f:
                    head = ''
                    for i, line in enumerate(f):
                        if i > 10:
                            break
                        head += line
                    if not all(key in head for key in search_keys):
                        continue

                    output_text = None
                    if with_output:
                        output_text = _extract_session_output(jsonl_file)

                    runs.append({
                        'time': datetime.fromtimestamp(mtime),
                        'session_id': jsonl_file.stem,
                        'output': output_text,
                    })
            except Exception:
                continue

    # Sort all runs by time descending (merged from multiple dirs)
    runs.sort(key=lambda r: r['time'], reverse=True)
    return runs[:20]


def _extract_session_output(jsonl_path):
    """Extract the last substantial assistant text from a session JSONL file."""
    last_text = None
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get('type') != 'assistant':
                        continue
                    msg = obj.get('message', {})
                    if not isinstance(msg, dict):
                        continue
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'text':
                                text = c.get('text', '').strip()
                                if len(text) > 40:
                                    last_text = text
                    elif isinstance(content, str) and len(content.strip()) > 40:
                        last_text = content.strip()
                except (json.JSONDecodeError, KeyError):
                    continue
    except Exception:
        pass
    return last_text


def get_next_run_time(schedule_str):
    """Calculate the next run time from a schedule string. Returns (datetime, human_str) or None."""
    now = datetime.now()

    if 'Always running' in schedule_str or 'Manual' in schedule_str:
        return None

    # Parse "Every Xh/Xm" intervals
    every_match = re.match(r'Every (\d+)(h|m|s)', schedule_str)
    if every_match:
        val, unit = int(every_match.group(1)), every_match.group(2)
        secs = val * {'h': 3600, 'm': 60, 's': 1}[unit]
        # Can't know exact next run for intervals, skip
        return None

    # Parse "Daily at HH:MM" or "Mon, Tue, ... at HH:MM"
    at_match = re.search(r'at\s+([\d:,\s]+)$', schedule_str)
    if not at_match:
        return None

    time_strs = [t.strip() for t in at_match.group(1).split(',')]
    day_part = schedule_str.split(' at ')[0].strip() if ' at ' in schedule_str else 'Daily'

    days_map = {'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6}

    if day_part == 'Daily':
        allowed_days = list(range(7))
    else:
        allowed_days = [days_map[d.strip()] for d in day_part.split(',') if d.strip() in days_map]
        if not allowed_days:
            allowed_days = list(range(7))

    # Find next occurrence
    candidates = []
    for day_offset in range(8):  # check up to a week ahead
        candidate_date = now + timedelta(days=day_offset)
        if candidate_date.weekday() not in allowed_days:
            continue
        for ts in time_strs:
            try:
                parts = ts.split(':')
                h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                candidate = candidate_date.replace(hour=h, minute=m, second=0, microsecond=0)
                if candidate > now:
                    candidates.append(candidate)
            except (ValueError, IndexError):
                continue

    if not candidates:
        return None

    next_run = min(candidates)
    diff = next_run - now
    total_mins = int(diff.total_seconds() / 60)
    if total_mins < 60:
        human = f'{total_mins}m'
    elif total_mins < 1440:
        h = total_mins // 60
        m = total_mins % 60
        human = f'{h}h {m}m' if m else f'{h}h'
    else:
        d = total_mins // 1440
        h = (total_mins % 1440) // 60
        human = f'{d}d {h}h' if h else f'{d}d'

    return (next_run, human)


def get_reliability_strip(prompt, days=14):
    """Build a 14-day reliability strip: list of (date, ran_bool) tuples."""
    runs = get_run_history(prompt, days=days)
    run_dates = set()
    for r in runs:
        run_dates.add(r['time'].date())

    today = datetime.now().date()
    strip = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        strip.append((d, d in run_dates))
    return strip


def _time_ago(dt):
    """Return a human-readable relative time string."""
    diff = datetime.now() - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return 'just now'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h ago'
    days = hours // 24
    if days < 7:
        return f'{days}d ago'
    weeks = days // 7
    return f'{weeks}w ago'


def smart_date(ts):
    """Return relative time for recent items, short absolute for older ones."""
    dt = datetime.fromtimestamp(ts)
    diff = datetime.now() - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return 'just now'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h ago'
    days = hours // 24
    if days < 7:
        return f'{days}d ago'
    return dt.strftime('%b %-d')


def generate_timeline_svg(jobs):
    """Generate a 24-hour SVG timeline of scheduled tasks with staggered labels."""
    now = datetime.now()
    current_hour = now.hour + now.minute / 60.0
    now_label = now.strftime('%-H:%M')

    # Collect task dots: (hour_float, label, is_always_running)
    task_dots = []
    for job in jobs:
        sched = job.get('schedule', '')
        label_short = _strip_label_prefixes(job.get('label', ''))
        label_short = label_short.replace('-', ' ')

        if 'Always running' in sched:
            task_dots.append((None, label_short, True))
            continue

        if ' at ' in sched:
            time_part = sched.split(' at ')[-1].strip()
            for tp in time_part.split(', '):
                try:
                    parts = tp.strip().split(':')
                    h = int(parts[0])
                    m = int(parts[1]) if len(parts) > 1 else 0
                    task_dots.append((h + m / 60.0, label_short, False))
                except (ValueError, IndexError):
                    pass
        elif 'Every ' in sched:
            task_dots.append((None, label_short, True))

    width = 1000
    label_zone = 70   # space above track for task labels
    track_y = label_zone + 8
    height = track_y + 36  # space below for hour labels
    margin_x = 50
    track_width = width - 2 * margin_x

    svg = []
    svg.append(f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" '
               f'xmlns="http://www.w3.org/2000/svg" style="max-width:{width}px; display:block; margin: 0 auto 24px;">')

    svg.append('<defs>'
               '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
               '<feGaussianBlur stdDeviation="3" result="blur"/>'
               '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
               '</filter>'
               '<filter id="glow-strong" x="-50%" y="-50%" width="200%" height="200%">'
               '<feGaussianBlur stdDeviation="5" result="blur"/>'
               '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
               '</filter>'
               '</defs>')

    # Track line
    svg.append(f'<line x1="{margin_x}" y1="{track_y}" x2="{width - margin_x}" y2="{track_y}" '
               f'stroke="#3D3835" stroke-width="1.5"/>')

    # Hour markers (every 6 hours) — below the track
    for h in [0, 6, 12, 18, 24]:
        x = margin_x + (h / 24.0) * track_width
        svg.append(f'<line x1="{x}" y1="{track_y - 4}" x2="{x}" y2="{track_y + 4}" stroke="#78716C" stroke-width="1"/>')
        if h < 24:
            svg.append(f'<text x="{x}" y="{track_y + 20}" text-anchor="middle" '
                       f'fill="#78716C" font-family="JetBrains Mono, monospace" font-size="10">{h:02d}:00</text>')

    # Subtle hour ticks
    for h in range(25):
        if h % 6 == 0:
            continue
        x = margin_x + (h / 24.0) * track_width
        svg.append(f'<line x1="{x}" y1="{track_y - 2}" x2="{x}" y2="{track_y + 2}" stroke="#2D2926" stroke-width="0.5"/>')

    # Past dimming overlay
    current_x = margin_x + (current_hour / 24.0) * track_width
    svg.append(f'<rect x="{margin_x}" y="{track_y - 8}" width="{current_x - margin_x}" height="16" '
               f'fill="#1C1917" opacity="0.3" rx="2"/>')

    # --- Task dots with staggered labels above the track ---
    # Sort timed tasks by hour so we can stagger overlapping labels
    timed_dots = [(h, l) for h, l, a in task_dots if not a and h is not None]
    timed_dots.sort(key=lambda d: d[0])

    # Assign label rows: stagger labels that would overlap (within ~2.5 hours of each other)
    label_rows = []  # list of (hour, label, row_index)
    for hour, label in timed_dots:
        # Find the lowest row where this label doesn't overlap with existing labels
        row = 0
        while True:
            conflict = False
            for oh, ol, orow in label_rows:
                if orow == row and abs(hour - oh) < 2.5:
                    conflict = True
                    break
            if not conflict:
                break
            row += 1
        label_rows.append((hour, label, row))

    max_row = max((r for _, _, r in label_rows), default=0)

    for hour, label, row in label_rows:
        x = margin_x + (hour / 24.0) * track_width
        is_past = hour < current_hour
        opacity = "0.45" if is_past else "0.9"

        # Dot on the track
        svg.append(f'<circle cx="{x}" cy="{track_y}" r="4.5" fill="#D4A574" opacity="{opacity}"/>')

        # Connector line from dot up to label
        label_y = label_zone - (row * 18)
        svg.append(f'<line x1="{x}" y1="{track_y - 5}" x2="{x}" y2="{label_y + 4}" '
                   f'stroke="#3D3835" stroke-width="0.7" opacity="{opacity}"/>')

        # Label text
        time_str = f'{int(hour):02d}:{int((hour % 1) * 60):02d}'
        svg.append(f'<text x="{x}" y="{label_y}" text-anchor="middle" '
                   f'fill="#A8A29E" font-family="JetBrains Mono, monospace" font-size="9" '
                   f'opacity="{opacity}">{label}</text>')
        svg.append(f'<text x="{x}" y="{label_y - 11}" text-anchor="middle" '
                   f'fill="#78716C" font-family="JetBrains Mono, monospace" font-size="8" '
                   f'opacity="{opacity}">{time_str}</text>')

    # Always-running tasks — dashed line above track
    always_tasks = [l for _, l, a in task_dots if a]
    if always_tasks:
        svg.append(f'<line x1="{margin_x}" y1="{track_y - 7}" x2="{width - margin_x}" y2="{track_y - 7}" '
                   f'stroke="#D4A574" stroke-width="0.5" opacity="0.3" stroke-dasharray="3 5"/>')

    # --- Current time marker (prominent) ---
    # Vertical line spanning full height
    svg.append(f'<line x1="{current_x}" y1="4" x2="{current_x}" y2="{track_y + 6}" '
               f'stroke="#D4A574" stroke-width="1.5" opacity="0.3"/>')
    # Bold segment near the track
    svg.append(f'<line x1="{current_x}" y1="{track_y - 12}" x2="{current_x}" y2="{track_y + 12}" '
               f'stroke="#D4A574" stroke-width="2.5" filter="url(#glow-strong)"/>')
    # Diamond marker on the track
    svg.append(f'<polygon points="{current_x},{track_y - 6} {current_x + 4},{track_y} '
               f'{current_x},{track_y + 6} {current_x - 4},{track_y}" '
               f'fill="#D4A574" filter="url(#glow)"/>')
    # "Now" label below
    svg.append(f'<text x="{current_x}" y="{track_y + 28}" text-anchor="middle" '
               f'fill="#D4A574" font-family="JetBrains Mono, monospace" font-size="10" '
               f'font-weight="600">{now_label}</text>')

    svg.append('</svg>')
    return '\n'.join(svg)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#1C1917">
<link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%2020%2020'%20fill='none'%20stroke='%23D4A574'%20stroke-width='1.5'%20stroke-linecap='round'%20stroke-linejoin='round'%3E%3Cpath%20d='M10%205.2C8.4%204%206.2%203.5%203.5%203.5v10.3c2.7%200%204.9.5%206.5%201.7'/%3E%3Cpath%20d='M10%205.2c1.6-1.2%203.8-1.7%206.5-1.7v10.3c-2.7%200-4.9.5-6.5%201.7'/%3E%3Cpath%20d='M10%205.2v10.3'/%3E%3C/svg%3E">
<title>PAGE_TITLE</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,700;1,7..72,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.1/marked.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/mode/markdown/markdown.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/edit/continuelist.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/search/search.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/search/searchcursor.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/search/jump-to-line.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/dialog/dialog.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/dialog/dialog.min.css">
<style>
  :root {
    --bg-primary: #1C1917;
    --bg-sidebar: #1A1614;
    --bg-surface: #292524;
    --bg-elevated: #332E2B;
    --text-primary: #E7E5E4;
    --text-secondary: #A8A29E;
    --text-tertiary: #78716C;
    --accent: #D4A574;
    --accent-hover: #E0B88A;
    --border: #3D3835;
    --border-subtle: #2D2926;
    --status-green: #86EFAC;
    --status-amber: #FCD34D;
    --font-prose: 'Literata', Georgia, serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', monospace;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font-mono);
    background: var(--bg-primary); color: var(--text-primary);
    display: flex; height: 100vh;
  }

  /* Subtle crosshatch texture */
  body::before {
    content: '';
    position: fixed; inset: 0; pointer-events: none; z-index: 9999;
    opacity: 0.025;
    background-image: url("data:image/svg+xml,%3Csvg width='8' height='8' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M0 0l8 8M8 0l-8 8' stroke='%23E7E5E4' stroke-width='0.5'/%3E%3C/svg%3E");
    background-size: 8px 8px;
  }

  a { color: var(--accent); text-decoration: none; transition: color 150ms ease; }
  a:hover { color: var(--accent-hover); }

  /* Sidebar */
  .sidebar {
    width: 220px; min-width: 220px; background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    display: flex; flex-direction: column; overflow-y: auto;
    padding-top: 20px;
  }
  .sidebar-rule {
    border: none; border-top: 1px solid var(--border-subtle);
    margin: 0 14px 8px;
  }
  .sidebar a {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; color: var(--text-secondary); font-size: 13px;
    border-left: 3px solid transparent;
    transition: color 150ms ease, border-color 150ms ease;
  }
  .sidebar a:hover { color: var(--text-primary); background: var(--bg-elevated); }
  .sidebar a.active {
    color: var(--accent); border-left-color: var(--accent);
  }
  .sidebar .icon {
    width: 20px; height: 20px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-tertiary);
  }
  .sidebar a:hover .icon, .sidebar a.active .icon { color: var(--accent); }

  /* Main content */
  .main { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }

  /* Breadcrumb */
  .breadcrumb {
    padding: 12px 32px; font-size: 13px;
    display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  }
  .breadcrumb a { color: var(--text-secondary); }
  .breadcrumb a:hover { color: var(--accent); }
  .breadcrumb a:last-child { color: var(--text-primary); }
  .breadcrumb .sep { color: var(--text-tertiary); margin: 0 2px; }

  /* Directory listing */
  .listing { padding: 16px 32px; }
  .listing table { width: 100%; border-collapse: collapse; }
  .listing td {
    padding: 10px 12px; font-size: 14px;
    border-left: 2px solid transparent;
    transition: border-color 150ms ease, background 150ms ease;
  }
  .listing tr:hover td {
    background: rgba(41, 37, 36, 0.5);
    border-left-color: var(--accent);
  }
  .listing .name { display: flex; align-items: center; gap: 10px; }
  .listing .name a { color: var(--text-primary); }
  .listing .name a:hover { color: var(--accent); }
  .listing .icon {
    width: 16px; height: 16px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-secondary);
  }
  .listing tr:hover .icon { color: var(--accent); }
  .listing .size, .listing .date { color: var(--text-secondary); font-size: 12px; }

  /* Directory filter + sort control row — kept quiet */
  .listing-controls {
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; padding: 0 12px 10px 12px; margin-bottom: 2px;
  }
  .listing-filter {
    font-family: 'JetBrains Mono', monospace; font-size: 12px;
    color: var(--text-primary); background: transparent;
    border: 1px solid var(--border-subtle); border-radius: 4px;
    padding: 5px 9px; width: 200px; outline: none;
    transition: border-color 150ms ease;
  }
  .listing-filter::placeholder { color: var(--text-tertiary); }
  .listing-filter:focus { border-color: var(--accent); }
  .listing-sort { display: flex; align-items: center; gap: 12px; }
  .sort-btn {
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--text-tertiary); background: transparent;
    border: none; padding: 0; cursor: pointer;
    transition: color 150ms ease;
  }
  .sort-btn:hover { color: var(--text-secondary); }
  .sort-btn.active { color: var(--accent); }
  .listing-count {
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--text-tertiary); margin-left: 4px;
  }

  /* File content */
  .file-content { padding: 24px 40px; flex: 1; }
  .file-content .filename {
    font-size: 13px; color: var(--text-secondary); margin-bottom: 16px;
    padding-bottom: 8px; border-bottom: 1px solid var(--border-subtle);
  }

  /* Markdown rendering */
  .markdown-body {
    max-width: 720px; line-height: 1.75; font-size: 16px;
    font-family: var(--font-prose);
  }
  .markdown-body h1 {
    font-size: 28px; font-weight: 700; line-height: 1.3;
    margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border-subtle);
    font-family: var(--font-prose);
  }
  .markdown-body h2 {
    font-size: 22px; font-weight: 700; line-height: 1.35;
    margin: 20px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border-subtle);
    font-family: var(--font-prose);
  }
  .markdown-body h3 { font-size: 18px; font-weight: 700; margin: 16px 0 8px; font-family: var(--font-prose); }
  .markdown-body p { margin: 10px 0; }
  .markdown-body ul, .markdown-body ol { margin: 10px 0; padding-left: 24px; }
  .markdown-body li { margin: 4px 0; }
  .markdown-body code {
    background: var(--bg-surface); padding: 2px 6px; border-radius: 4px;
    font-family: var(--font-mono); font-size: 0.85em;
  }
  .markdown-body pre {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: 6px;
    padding: 16px; overflow-x: auto; margin: 12px 0;
  }
  .markdown-body pre code {
    background: none; padding: 0;
    font-family: var(--font-mono); font-size: 13px; line-height: 1.5;
  }
  .markdown-body blockquote {
    border-left: 3px solid var(--accent); padding-left: 16px;
    color: var(--text-secondary); margin: 10px 0;
    font-style: italic; font-size: 15px; line-height: 1.7;
  }
  .markdown-body table { border-collapse: collapse; margin: 12px 0; }
  .markdown-body th, .markdown-body td {
    border: 1px solid var(--border); padding: 8px 12px; text-align: left;
  }
  .markdown-body th { background: var(--bg-surface); }
  .markdown-body strong { color: var(--text-primary); }
  .markdown-body hr { border: none; border-top: 1px solid var(--border-subtle); margin: 20px 0; }
  .markdown-body img { max-width: 100%; border-radius: 6px; }
  .markdown-body a { color: var(--accent); }
  .markdown-body a:hover { color: var(--accent-hover); }

  /* Code file rendering */
  .code-body pre {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: 6px;
    padding: 16px; overflow-x: auto; font-size: 13px; line-height: 1.5;
    font-family: var(--font-mono);
  }

  /* Edit mode */
  .edit-bar {
    display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
  }
  .edit-bar button {
    padding: 6px 16px; border-radius: 6px; border: 1px solid var(--border);
    font-size: 13px; cursor: pointer; font-family: var(--font-mono);
    transition: background 150ms ease;
  }
  .btn-edit {
    background: var(--accent); color: var(--bg-primary); border-color: var(--accent);
  }
  .btn-edit:hover { background: var(--accent-hover); }
  .btn-save {
    background: var(--accent); color: var(--bg-primary); border-color: var(--accent);
  }
  .btn-save:hover { background: var(--accent-hover); }
  .btn-cancel {
    background: var(--bg-surface); color: var(--text-primary);
  }
  .btn-cancel:hover { background: var(--bg-elevated); }
  #edit-area { display: flex; flex-direction: column; height: calc(100vh - 120px); }
  #cm-editor { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex: 1; min-height: 0; }
  #cm-editor .CodeMirror {
    height: 100%; background: var(--bg-sidebar); color: var(--text-primary);
    font-family: var(--font-mono); font-size: 14px; line-height: 1.6;
  }
  #cm-editor .CodeMirror-gutters {
    background: var(--bg-sidebar); border-right: 1px solid var(--border-subtle);
    color: var(--text-tertiary);
  }
  #cm-editor .CodeMirror-linenumber { color: var(--text-tertiary); font-size: 12px; }
  #cm-editor .CodeMirror-activeline-background { background: rgba(212, 165, 116, 0.05); }
  #cm-editor .CodeMirror-activeline-gutter .CodeMirror-linenumber { color: var(--accent); }
  #cm-editor .CodeMirror-selected { background: rgba(212, 165, 116, 0.15) !important; }
  #cm-editor .CodeMirror-focused .CodeMirror-selected { background: rgba(212, 165, 116, 0.2) !important; }
  #cm-editor .CodeMirror-cursor { border-left-color: var(--accent); }
  #cm-editor .CodeMirror-matchingbracket { color: var(--accent) !important; text-decoration: underline; }
  #cm-editor .cm-header { color: var(--accent); font-weight: 700; }
  #cm-editor .cm-header-1 { font-size: 1.3em; }
  #cm-editor .cm-header-2 { font-size: 1.15em; }
  #cm-editor .cm-header-3 { font-size: 1.05em; }
  #cm-editor .cm-strong { color: var(--text-primary); font-weight: 700; }
  #cm-editor .cm-em { color: var(--text-secondary); font-style: italic; }
  #cm-editor .cm-link { color: var(--accent); }
  #cm-editor .cm-url { color: var(--text-tertiary); }
  #cm-editor .cm-comment { color: var(--text-tertiary); }
  #cm-editor .cm-quote { color: var(--text-secondary); font-style: italic; }
  #cm-editor .cm-formatting { color: var(--text-tertiary); }
  #cm-editor .CodeMirror-dialog { background: var(--bg-surface); border-bottom: 1px solid var(--border); color: var(--text-primary); padding: 4px 8px; }
  #cm-editor .CodeMirror-dialog input { background: var(--bg-sidebar); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px; font-family: var(--font-mono); }
  .save-status {
    font-size: 13px; color: var(--status-green); display: none;
  }

  /* Scheduled tasks */
  .tasks-page { padding: 24px 32px; }
  .tasks-page h1 { font-size: 1.5em; margin-bottom: 4px; font-family: var(--font-prose); }
  .tasks-page .subtitle { color: var(--text-secondary); font-size: 13px; margin-bottom: 24px; }
  .task-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 16px;
  }
  .task-card {
    background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 8px;
    padding: 24px; cursor: pointer;
    border-left: 3px solid transparent;
    transition: border-color 150ms ease;
  }
  .task-card:hover { border-left-color: var(--accent); }
  .task-card.status-running { border-left-color: var(--accent); }
  .task-card.status-loaded { border-left-color: var(--status-green); }
  .task-card .task-name {
    font-size: 14px; font-weight: 500; color: var(--text-primary); margin-bottom: 6px;
  }
  .task-card .task-desc {
    font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 12px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    font-family: var(--font-prose);
  }
  .task-card .task-schedule {
    display: inline-block; font-size: 11px; padding: 3px 10px; border-radius: 12px;
    font-weight: 500;
  }
  .task-schedule.running { background: rgba(212, 165, 116, 0.15); color: var(--accent); }
  .task-schedule.scheduled { background: rgba(134, 239, 172, 0.1); color: var(--status-green); }
  .task-card .task-meta {
    display: flex; align-items: center; justify-content: space-between; margin-top: 10px;
  }
  .task-card .task-last-run { font-size: 11px; color: var(--text-tertiary); }
  .status-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;
  }
  .status-dot.green { background: var(--status-green); }
  .status-dot.amber { background: var(--accent); animation: pulse 3s ease-in-out infinite; }
  .status-dot.gray { background: var(--text-tertiary); }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

  /* Hamburger menu button (hidden on desktop) */
  .hamburger {
    display: none; position: fixed; top: 10px; left: 10px; z-index: 1000;
    background: var(--bg-surface); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text-primary); font-size: 22px; width: 40px; height: 40px;
    cursor: pointer; align-items: center; justify-content: center; line-height: 1;
  }
  .sidebar-overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 998;
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    body { flex-direction: column; }
    .hamburger { display: flex; }
    .sidebar {
      position: fixed; left: -240px; top: 0; bottom: 0; z-index: 999;
      width: 220px; min-width: 220px; transition: left 0.25s ease;
    }
    .sidebar.open { left: 0; }
    .sidebar-overlay.open { display: block; }
    .main { width: 100%; }
    .breadcrumb { padding: 12px 16px; padding-left: 56px; font-size: 12px; }
    .listing { padding: 8px 12px; }
    .listing td:nth-child(3) { display: none; }
    .listing td { padding: 8px; font-size: 13px; }
    .file-content { padding: 16px; }
    .markdown-body { font-size: 15px; }
    .markdown-body pre { padding: 10px; }
    .markdown-body pre code { font-size: 12px; }
    .code-body pre { font-size: 11px; padding: 10px; }
    .tasks-page { padding: 16px; }
    .tasks-page h1 { font-size: 1.3em; }
    .task-grid { grid-template-columns: 1fr; gap: 12px; }
    .task-detail { padding: 16px; }
    .task-detail h1 { font-size: 1.2em; }
    .detail-grid { grid-template-columns: 1fr; }
    .log-box { font-size: 11px; padding: 10px; max-height: 300px; }
    #cm-editor .CodeMirror { font-size: 12px; }
    #edit-area { height: calc(100vh - 100px); }
  }

  /* Task detail page — redesigned agent view */
  .task-detail { padding: 24px 32px; max-width: 960px; }
  .task-detail-header { margin-bottom: 24px; }
  .task-detail-header h1 {
    font-size: 1.6em; margin-bottom: 6px; font-family: var(--font-prose);
    display: flex; align-items: center; gap: 12px;
  }
  .task-detail-header .task-desc {
    color: var(--text-secondary); font-size: 14px; font-family: var(--font-prose);
    line-height: 1.5; margin-bottom: 12px;
  }
  .task-detail-back {
    color: var(--text-tertiary); font-size: 12px; margin-bottom: 16px; display: block;
    transition: color 150ms ease;
  }
  .task-detail-back:hover { color: var(--text-secondary); }

  /* Status bar — compact row of status + schedule + next run + reliability */
  .task-status-bar {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    margin-bottom: 28px; padding: 14px 18px;
    background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px;
  }
  .task-status-bar .status-chip {
    display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500;
  }
  .task-status-bar .schedule-chip {
    font-size: 12px; color: var(--text-secondary);
    padding: 3px 10px; border-radius: 12px;
    background: rgba(134, 239, 172, 0.08); border: 1px solid rgba(134, 239, 172, 0.15);
  }
  .task-status-bar .schedule-chip.always {
    background: rgba(212, 165, 116, 0.1); border-color: rgba(212, 165, 116, 0.2);
    color: var(--accent);
  }
  .task-status-bar .divider {
    width: 1px; height: 20px; background: var(--border-subtle);
  }
  .task-status-bar .next-run {
    font-size: 12px; color: var(--text-tertiary);
    display: flex; align-items: center; gap: 6px;
  }
  .task-status-bar .next-run .countdown {
    color: var(--accent); font-weight: 500; font-family: var(--font-mono);
  }

  /* Reliability strip */
  .reliability-strip {
    display: flex; align-items: center; gap: 3px; margin-left: auto;
  }
  .reliability-strip .strip-dot {
    width: 8px; height: 8px; border-radius: 2px; transition: transform 150ms ease;
  }
  .reliability-strip .strip-dot:hover { transform: scale(1.5); }
  .reliability-strip .strip-dot.ran { background: var(--status-green); opacity: 0.8; }
  .reliability-strip .strip-dot.missed { background: var(--bg-elevated); border: 1px solid var(--border-subtle); }
  .reliability-strip .strip-dot.today { box-shadow: 0 0 0 1.5px var(--accent); }
  .reliability-strip .strip-label {
    font-size: 10px; color: var(--text-tertiary); margin-right: 6px; white-space: nowrap;
  }

  /* Latest output hero */
  .latest-output {
    margin-bottom: 28px;
  }
  .latest-output .section-label {
    font-size: 11px; color: var(--text-tertiary); text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 10px; font-weight: 500;
    display: flex; align-items: center; gap: 8px;
  }
  .latest-output .section-label .pulse-dot {
    width: 6px; height: 6px; border-radius: 50%; background: var(--status-green);
    animation: pulse 3s ease-in-out infinite;
  }
  .latest-output .output-card {
    background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 10px;
    padding: 24px; position: relative; overflow: hidden;
  }
  .latest-output .output-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    background: linear-gradient(to bottom, var(--accent), var(--status-green));
    border-radius: 3px 0 0 3px;
  }
  .latest-output .output-meta {
    display: flex; align-items: center; gap: 10px; margin-bottom: 14px;
    font-size: 12px; color: var(--text-tertiary);
  }
  .latest-output .output-meta .timestamp { font-family: var(--font-mono); }
  .latest-output .output-text {
    font-size: 14px; line-height: 1.75; color: var(--text-primary);
    font-family: var(--font-prose);
    max-height: 300px; overflow-y: auto;
    mask-image: linear-gradient(to bottom, black 85%, transparent 100%);
    -webkit-mask-image: linear-gradient(to bottom, black 85%, transparent 100%);
  }
  .latest-output .output-text.expanded {
    max-height: none;
    mask-image: none; -webkit-mask-image: none;
  }
  .latest-output .expand-btn {
    display: inline-block; margin-top: 10px; font-size: 12px; color: var(--accent);
    cursor: pointer; background: none; border: none; font-family: var(--font-mono);
    padding: 0;
  }
  .latest-output .expand-btn:hover { color: var(--accent-hover); }
  .latest-output .no-output {
    color: var(--text-tertiary); font-style: italic; font-size: 13px;
    font-family: var(--font-prose);
  }

  /* Output feed — vertical timeline of past runs */
  .output-feed { margin-bottom: 28px; }
  .output-feed .section-label {
    font-size: 11px; color: var(--text-tertiary); text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 14px; font-weight: 500;
  }
  .feed-timeline { position: relative; padding-left: 24px; }
  .feed-timeline::before {
    content: ''; position: absolute; left: 7px; top: 8px; bottom: 8px;
    width: 1px; background: var(--border-subtle);
  }
  .feed-item {
    position: relative; margin-bottom: 16px; cursor: pointer;
  }
  .feed-item::before {
    content: ''; position: absolute; left: -20px; top: 8px;
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--bg-surface); border: 2px solid var(--accent);
    transition: background 150ms ease;
  }
  .feed-item:first-child::before { background: var(--accent); }
  .feed-item .feed-meta {
    font-size: 11px; color: var(--text-tertiary); margin-bottom: 4px;
    font-family: var(--font-mono);
    display: flex; align-items: center; gap: 8px;
  }
  .feed-item .feed-meta .feed-ago { color: var(--text-tertiary); opacity: 0.7; }
  .feed-item .feed-summary {
    font-size: 13px; line-height: 1.6; color: var(--text-secondary);
    font-family: var(--font-prose);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    transition: color 150ms ease;
  }
  .feed-item:hover .feed-summary { color: var(--text-primary); }
  .feed-item .feed-full {
    display: none; font-size: 13px; line-height: 1.7; color: var(--text-primary);
    font-family: var(--font-prose); margin-top: 8px;
    background: var(--bg-surface); border: 1px solid var(--border-subtle);
    border-radius: 8px; padding: 16px; max-height: 400px; overflow-y: auto;
    white-space: pre-wrap; word-wrap: break-word;
  }
  .feed-item.expanded .feed-summary { display: none; }
  .feed-item.expanded .feed-full { display: block; }

  /* Collapsible config section */
  .config-section { margin-top: 8px; }
  .config-toggle {
    display: flex; align-items: center; gap: 8px; cursor: pointer;
    font-size: 12px; color: var(--text-tertiary); text-transform: uppercase;
    letter-spacing: 0.8px; font-weight: 500; margin-bottom: 14px;
    background: none; border: none; font-family: var(--font-mono); padding: 0;
    transition: color 150ms ease;
  }
  .config-toggle:hover { color: var(--text-secondary); }
  .config-toggle .chevron {
    transition: transform 200ms ease; display: inline-block; font-size: 10px;
  }
  .config-toggle.open .chevron { transform: rotate(90deg); }
  .config-body { display: none; }
  .config-body.open { display: block; }

  .detail-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px;
  }
  .detail-item {
    background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 12px;
  }
  .detail-item .label { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 3px; }
  .detail-item .value { font-size: 12px; color: var(--text-primary); }
  .detail-item .value a { color: var(--accent); }

  /* Prompt section */
  .prompt-section { margin-bottom: 20px; }
  .prompt-section h3 { font-size: 12px; margin-bottom: 10px; color: var(--text-secondary); font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 0.5px; }
  .prompt-box {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: 8px;
    padding: 18px; font-size: 13px; line-height: 1.75; color: var(--text-secondary);
    white-space: pre-wrap; word-wrap: break-word;
    font-family: var(--font-prose); max-height: 300px; overflow-y: auto;
  }
  .prompt-box .bash-var { color: var(--accent); font-weight: 500; font-family: var(--font-mono); }

  /* Log sections */
  .log-section { margin-top: 16px; }
  .log-section h3 { font-size: 12px; margin-bottom: 8px; color: var(--text-secondary); font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 0.5px; }
  .log-box {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: 6px;
    padding: 14px; font-family: var(--font-mono);
    font-size: 11px; line-height: 1.6; max-height: 400px; overflow-y: auto;
    white-space: pre-wrap; word-break: break-all; color: var(--text-tertiary);
  }
  .log-box .log-empty { color: var(--text-tertiary); font-style: italic; }

  /* Run history (fallback for tasks without session matching) */
  .run-history-section { margin-bottom: 24px; }
  .run-history-section h2 { font-size: 1.1em; margin-bottom: 12px; color: var(--text-primary); font-family: var(--font-prose); }
  .run-list {
    list-style: none; background: var(--bg-surface); border: 1px solid var(--border-subtle);
    border-radius: 6px; overflow: hidden;
    position: relative;
  }
  .run-list::before {
    content: ''; position: absolute; left: 24px; top: 0; bottom: 0;
    width: 1px; background: var(--border-subtle);
  }
  .run-list li {
    padding: 10px 16px 10px 40px; border-bottom: 1px solid var(--border-subtle);
    font-size: 12px; color: var(--text-primary); display: flex; align-items: center; gap: 10px;
    position: relative;
  }
  .run-list li::before {
    content: ''; position: absolute; left: 21px; top: 50%;
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent); transform: translateY(-50%);
  }
  .run-list li:last-child { border-bottom: none; }
  .run-list .run-time { font-family: var(--font-mono); color: var(--text-secondary); font-size: 12px; }
  .run-list .run-ago { color: var(--text-tertiary); font-size: 11px; }

  /* Diary entry listing — special date formatting */
  .diary-date { font-family: var(--font-prose); font-style: italic; }

  /* Hero section for home page */
  .hero-section {
    padding: 32px 32px 0;
    text-align: center;
  }
  .hero-section img {
    max-width: 100%; height: auto; max-height: 260px;
    border-radius: 8px; opacity: 0.9;
  }

  /* highlight.js warm overrides */
  .hljs { background: var(--bg-sidebar) !important; }
  .hljs-keyword, .hljs-selector-tag { color: var(--accent) !important; }
  .hljs-string, .hljs-addition { color: #A3BE8C !important; }
  .hljs-comment, .hljs-quote { color: var(--text-tertiary) !important; }
  .hljs-number, .hljs-literal { color: #D08770 !important; }
  .hljs-title, .hljs-section { color: var(--accent-hover) !important; }
  .hljs-attr, .hljs-attribute { color: #EBCB8B !important; }

  /* ============================================================
     CONVERSATIONS TAB
     ============================================================ */

  /* Index page */
  .conv-index { max-width: 760px; margin: 0 auto; }
  .conv-index-header { text-align: center; margin-bottom: 32px; }
  .conv-index-header h1 {
    font-family: var(--font-prose); font-size: 32px; font-weight: 700;
    color: var(--text-primary); margin: 0 0 8px; letter-spacing: -0.01em;
  }
  .conv-index-header .subtitle {
    font-family: var(--font-mono); font-size: 14px; color: var(--text-tertiary); margin: 0;
  }

  /* Date group tabs — horizontal row, sticky */
  .conv-group-tabs {
    display: flex; gap: 0;
    border-bottom: 1px solid rgba(212, 165, 116, 0.35);
    margin-bottom: 0;
    position: sticky; top: 0; z-index: 10;
    background: var(--bg-primary);
  }
  .conv-group-tabs .group-tab {
    font-family: var(--font-mono); font-size: 12px; font-weight: 500;
    color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em;
    padding: 12px 24px; cursor: pointer; position: relative;
    border-bottom: 2px solid transparent; transition: color 0.15s;
    white-space: nowrap; margin-bottom: -1px;
    text-decoration: none;
  }
  .conv-group-tabs .group-tab:hover { color: var(--text-secondary); }
  .conv-group-tabs .group-tab.active {
    color: var(--accent); border-bottom-color: var(--accent);
  }

  /* Section label inside each group */
  .conv-section-label {
    font-family: var(--font-mono); font-size: 11px; font-weight: 500;
    color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em;
    padding: 16px 20px 8px;
  }

  .conv-group-section {
    display: block;
    scroll-margin-top: 48px;
  }
  .conv-group-section + .conv-group-section {
    border-top: 1px solid var(--border-subtle);
  }

  /* Fallback stacked groups */
  .conv-date-group { margin-bottom: 0; }
  .conv-date-group .group-label {
    font-family: var(--font-mono); font-size: 11px; font-weight: 500;
    color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em;
    padding: 12px 0 8px; margin-bottom: 0; border-bottom: 1px solid var(--border);
  }

  .conv-row {
    display: flex; align-items: center; gap: 14px;
    padding: 18px 20px; border-bottom: 1px solid rgba(212, 165, 116, 0.12);
    text-decoration: none; color: inherit;
    cursor: pointer; transition: background 0.12s;
  }
  .conv-row:last-child { border-bottom: none; }
  .conv-row:hover { background: rgba(212, 165, 116, 0.10); }

  .conv-row .conv-marker {
    flex-shrink: 0; width: 16px; height: 16px; color: var(--accent); opacity: 0.5;
  }
  .conv-row:hover .conv-marker { opacity: 1; }

  .conv-row .conv-time {
    font-family: var(--font-mono); font-size: 14px; font-weight: 600;
    color: var(--text-primary); min-width: 44px; flex-shrink: 0;
  }
  .conv-row .conv-info { flex: 1; min-width: 0; overflow: hidden; }
  .conv-row .conv-preview {
    font-family: var(--font-prose); font-size: 15px; color: var(--text-primary);
    line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    display: block;
  }
  .conv-row .conv-size {
    font-family: var(--font-mono); font-size: 12px; color: var(--text-tertiary);
    min-width: 56px; text-align: right; flex-shrink: 0;
  }

  /* Source badge chips + noise filter */
  .conv-badge {
    font-family: var(--font-mono); font-size: 10px; font-weight: 500;
    letter-spacing: 0.02em; line-height: 1;
    padding: 3px 7px; border-radius: 5px; flex-shrink: 0;
    border: 1px solid transparent; white-space: nowrap;
  }
  .conv-badge.kind-channel { background: rgba(212, 165, 116, 0.15); color: var(--accent); }
  .conv-badge.kind-dm { background: rgba(134, 239, 172, 0.1); color: var(--status-green); }
  .conv-badge.kind-scheduled { background: var(--bg-elevated); color: var(--text-tertiary); }
  .conv-badge.kind-terminal { background: transparent; color: var(--text-secondary); border-color: var(--border); }

  .conv-filter-bar {
    display: flex; gap: 8px; align-items: center;
    padding: 4px 0 14px;
  }
  .conv-filter-chip {
    font-family: var(--font-mono); font-size: 11px; font-weight: 500;
    letter-spacing: 0.03em; color: var(--text-tertiary);
    padding: 5px 12px; border-radius: 6px; cursor: pointer;
    background: transparent; border: 1px solid var(--border);
    transition: color 0.12s, background 0.12s, border-color 0.12s;
  }
  .conv-filter-chip:hover { color: var(--text-secondary); }
  .conv-filter-chip.active {
    background: rgba(212, 165, 116, 0.15); color: var(--accent);
    border-color: rgba(212, 165, 116, 0.35);
  }
  /* Filter modes toggle row visibility via container class */
  .conv-index.filter-conversations .conv-row[data-kind="scheduled"] { display: none; }
  .conv-index.filter-scheduled .conv-row:not([data-kind="scheduled"]) { display: none; }

  /* Detail page */
  .conv-detail { max-width: 760px; margin: 0 auto; }
  .conv-detail-back {
    font-family: var(--font-mono); font-size: 13px; color: var(--text-secondary);
    text-decoration: none; display: inline-block; margin-bottom: 16px;
  }
  .conv-detail-back:hover { color: var(--accent); }
  .conv-detail-header { margin-bottom: 32px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 20px; }
  .conv-detail-header h1 { font-family: var(--font-prose); font-size: 24px; font-weight: 700; margin: 0 0 10px; }
  .conv-detail-header .conv-header-meta {
    font-family: var(--font-mono); font-size: 12px; color: var(--text-tertiary);
    display: flex; gap: 16px; flex-wrap: wrap;
  }

  /* Live session indicator */
  .conv-live-indicator {
    display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--font-mono); font-size: 11px; color: var(--status-green);
    text-transform: lowercase; letter-spacing: 0.5px;
  }
  .conv-live-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--status-green);
    animation: pulse 3s ease-in-out infinite;
  }
  .conv-live-indicator.ended { color: var(--text-tertiary); }
  .conv-live-indicator.ended .conv-live-dot { background: var(--text-tertiary); animation: none; }

  /* Message blocks */
  .conv-message { margin-bottom: 0; padding: 0; }
  .conv-message + .conv-message.role-user { margin-top: 28px; }
  .conv-message.role-user + .conv-message.role-assistant { margin-top: 20px; }

  .conv-message.role-user .conv-text {
    background: rgba(212, 165, 116, 0.06);
    border-left: 3px solid var(--accent);
    padding: 16px 20px;
    border-radius: 0 6px 6px 0;
    margin: 8px 0 0;
  }
  .conv-message.role-user .conv-text .conv-markdown {
    font-family: var(--font-prose); font-size: 15px; line-height: 1.7;
    color: var(--text-primary);
  }

  .conv-message.role-assistant .conv-text {
    padding: 8px 0;
    margin: 4px 0;
  }
  .conv-message.role-assistant .conv-text .conv-markdown {
    font-family: var(--font-prose); font-size: 15px; line-height: 1.7;
    color: var(--text-primary);
  }

  /* Markdown inside conversations */
  .conv-markdown p { margin: 0 0 10px; }
  .conv-markdown p:last-child { margin-bottom: 0; }
  .conv-markdown code {
    font-family: var(--font-mono); font-size: 13px;
    background: var(--bg-surface); padding: 2px 5px; border-radius: 3px;
  }
  .conv-markdown pre { background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 14px; overflow-x: auto; margin: 10px 0; }
  .conv-markdown pre code { background: none; padding: 0; font-size: 13px; line-height: 1.5; }
  .conv-markdown h1, .conv-markdown h2, .conv-markdown h3 { font-family: var(--font-prose); color: var(--text-primary); margin: 16px 0 8px; }
  .conv-markdown h1 { font-size: 22px; }
  .conv-markdown h2 { font-size: 18px; }
  .conv-markdown h3 { font-size: 16px; }
  .conv-markdown ul, .conv-markdown ol { padding-left: 24px; margin: 8px 0; }
  .conv-markdown li { margin: 4px 0; }
  .conv-markdown blockquote { border-left: 3px solid var(--border); padding-left: 14px; color: var(--text-secondary); font-style: italic; margin: 10px 0; }
  .conv-markdown strong { font-weight: 700; }
  .conv-markdown a { color: var(--accent); text-decoration: none; }
  .conv-markdown a:hover { color: var(--accent-hover); text-decoration: underline; }
  .conv-markdown table { border-collapse: collapse; margin: 10px 0; width: 100%; }
  .conv-markdown th, .conv-markdown td { border: 1px solid var(--border-subtle); padding: 6px 10px; font-size: 14px; text-align: left; }
  .conv-markdown th { background: var(--bg-surface); font-weight: 500; }

  /* Thinking blocks */
  .conv-thinking {
    margin: 3px 0; border-radius: 6px; font-family: var(--font-mono); font-size: 11px;
  }
  .conv-thinking summary {
    cursor: pointer; color: var(--text-tertiary); padding: 4px 10px;
    display: flex; align-items: center; gap: 6px; user-select: none;
    border-radius: 6px; transition: background 0.15s; opacity: 0.6;
  }
  .conv-thinking summary:hover { background: var(--bg-surface); opacity: 1; color: var(--text-secondary); }
  .conv-thinking .thinking-icon { display: flex; align-items: center; }
  .conv-thinking .thinking-body {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle);
    border-radius: 0 0 6px 6px; padding: 12px 14px; margin-top: 2px;
  }
  .conv-thinking .thinking-body pre {
    margin: 0; white-space: pre-wrap; word-break: break-word;
    font-family: var(--font-mono); font-size: 12px; line-height: 1.6;
    color: var(--text-secondary);
  }

  /* Tool use blocks */
  .conv-tool-use {
    margin: 3px 0; border-radius: 6px; font-family: var(--font-mono); font-size: 12px;
  }
  .conv-tool-use summary {
    cursor: pointer; color: var(--text-secondary); padding: 6px 10px;
    display: flex; align-items: center; gap: 6px; user-select: none;
    border-radius: 6px; transition: background 0.15s;
  }
  .conv-tool-use[open] summary { background: var(--bg-surface); border-radius: 6px 6px 0 0; }
  .conv-tool-use summary:hover { background: var(--bg-surface); }
  .conv-tool-use .tool-icon { display: flex; align-items: center; color: var(--accent); opacity: 0.7; }
  .conv-tool-use .tool-name { font-weight: 500; color: var(--accent); }
  .conv-tool-use .tool-summary { color: var(--text-tertiary); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .conv-tool-use .tool-body {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-top: none;
    border-radius: 0 0 6px 6px; padding: 12px 14px; overflow-x: auto;
  }
  .conv-tool-use .tool-file { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; word-break: break-all; }
  .conv-tool-use .tool-desc { font-size: 12px; color: var(--text-secondary); margin-bottom: 8px; font-style: italic; }
  .conv-tool-use .tool-note { font-size: 12px; color: var(--text-tertiary); }
  .conv-tool-use .code-block pre {
    margin: 0; background: var(--bg-primary); border: 1px solid var(--border-subtle);
    border-radius: 4px; padding: 10px 12px; overflow-x: auto;
    font-size: 12px; line-height: 1.5; color: var(--text-primary);
  }

  /* Diff rendering */
  .diff-block pre {
    margin: 0; background: var(--bg-primary); border: 1px solid var(--border-subtle);
    border-radius: 4px; padding: 10px 12px; overflow-x: auto;
    font-size: 12px; line-height: 1.7;
  }
  .diff-add { color: #A3BE8C; display: block; background: rgba(163, 190, 140, 0.08); margin: 0 -12px; padding: 0 12px; }
  .diff-del { color: #BF616A; display: block; background: rgba(191, 97, 106, 0.08); margin: 0 -12px; padding: 0 12px; text-decoration: line-through; opacity: 0.7; }
  .diff-hunk { color: var(--text-tertiary); display: block; font-style: italic; }
  .diff-ctx { color: var(--text-secondary); display: block; }
  .diff-flag { color: var(--accent); font-weight: normal; font-size: 11px; }

  /* Tool result blocks */
  .conv-tool-result {
    margin: 0 0 3px; border-radius: 6px; font-family: var(--font-mono); font-size: 11px;
  }
  .conv-tool-result summary {
    cursor: pointer; color: var(--text-tertiary); padding: 4px 10px;
    display: flex; align-items: center; gap: 6px; user-select: none;
    border-radius: 6px; transition: background 0.15s; opacity: 0.7;
  }
  .conv-tool-result summary:hover { background: var(--bg-surface); opacity: 1; }
  .conv-tool-result .result-icon { display: flex; align-items: center; color: var(--status-green); }
  .conv-tool-result.tool-error .result-icon { color: #BF616A; }
  .conv-tool-result.tool-error summary { opacity: 1; }
  .conv-tool-result .result-preview { color: var(--text-tertiary); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 500px; }
  .conv-tool-result .result-body {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle);
    border-radius: 0 0 6px 6px; padding: 12px 14px; margin-top: 2px;
  }
  .conv-tool-result .result-body pre {
    margin: 0; white-space: pre-wrap; word-break: break-word;
    font-size: 12px; line-height: 1.5; color: var(--text-secondary);
  }

  /* Role label */
  .conv-role-label {
    font-family: var(--font-mono); font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em;
    padding: 0 0 6px; color: var(--text-tertiary);
    display: flex; align-items: center; gap: 8px;
  }
  .conv-message.role-user .conv-role-label { color: var(--accent); }
  .conv-role-label .conv-ts { font-weight: 400; text-transform: none; letter-spacing: 0; opacity: 0.6; font-size: 10px; }

  /* Load more button */
  .conv-load-more {
    font-family: var(--font-mono); font-size: 13px; color: var(--accent);
    background: var(--bg-surface); border: 1px solid var(--border);
    border-radius: 6px; padding: 10px 20px; cursor: pointer;
    display: block; margin: 24px auto; transition: background 0.15s;
  }
  .conv-load-more:hover { background: var(--bg-elevated); }

  #conv-sentinel {
    text-align: center; margin: 24px auto; min-height: 20px;
  }
  .conv-sentinel-label {
    font-family: var(--font-mono); font-size: 12px; color: var(--text-tertiary);
    letter-spacing: 0.02em;
  }

  /* Pagination — amber dots */
  .conv-pagination {
    display: flex; justify-content: center; gap: 10px; align-items: center;
    margin-top: 32px; padding-top: 0;
  }
  .conv-pagination > * {
    display: inline-block; width: 10px; height: 10px; min-width: 10px; min-height: 10px;
    border-radius: 50%; font-size: 0; line-height: 0; color: transparent;
    text-decoration: none; transition: all 0.15s; vertical-align: middle;
    background: rgba(212, 165, 116, 0.35);
  }
  .conv-pagination a:hover { background: var(--accent); transform: scale(1.3); cursor: pointer; }
  .conv-pagination .current { background: var(--accent); width: 11px; height: 11px; min-width: 11px; min-height: 11px; }

  /* Skill/meta messages — collapsed by default */
  .conv-meta-msg { margin: 6px 0; }
  .conv-skill-loaded {
    margin: 6px 18px; border-radius: 6px; font-family: var(--font-mono); font-size: 12px;
  }
  .conv-skill-loaded summary {
    cursor: pointer; color: var(--text-tertiary); padding: 8px 12px;
    display: flex; align-items: center; gap: 6px; user-select: none;
    background: var(--bg-surface); border: 1px solid var(--border-subtle);
    border-radius: 6px; transition: background 0.15s;
  }
  .conv-skill-loaded[open] summary { border-radius: 6px 6px 0 0; }
  .conv-skill-loaded summary:hover { background: var(--bg-elevated); color: var(--text-secondary); }
  .conv-skill-loaded .skill-icon { display: flex; align-items: center; color: var(--accent); }
  .conv-skill-loaded .skill-size { color: var(--text-tertiary); font-size: 11px; opacity: 0.7; }
  .conv-skill-loaded .skill-body {
    background: var(--bg-sidebar); border: 1px solid var(--border-subtle); border-top: none;
    border-radius: 0 0 6px 6px; padding: 12px 14px; max-height: 400px; overflow-y: auto;
  }

  /* Top bar with back + Slack button */
  .conv-detail-topbar {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 8px;
  }
  .conv-slack-btn {
    font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary);
    text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px;
    background: var(--bg-surface); transition: all 0.15s;
  }
  .conv-slack-btn:hover { color: var(--accent); border-color: var(--accent); background: var(--bg-elevated); }
  .conv-slack-btn svg { flex-shrink: 0; }

  /* --- Cmd+K search palette --- */
  #search-palette {
    display: none; position: fixed; inset: 0; z-index: 1000;
    background: rgba(0,0,0,0.5);
  }
  #search-palette.open { display: block; }
  .search-box {
    position: absolute; top: 15vh; left: 50%; transform: translateX(-50%);
    width: 90%; max-width: 640px;
    background: var(--bg-surface); border: 1px solid var(--border);
    border-radius: 10px; overflow: hidden;
    display: flex; flex-direction: column;
  }
  #search-input {
    width: 100%; border: none; outline: none;
    background: transparent; color: var(--text-primary);
    font-family: var(--font-mono); font-size: 15px;
    padding: 16px 18px;
    border-bottom: 1px solid var(--border-subtle);
  }
  #search-input::placeholder { color: var(--text-tertiary); }
  #search-results {
    list-style: none; max-height: 52vh; overflow-y: auto;
    margin: 0; padding: 6px 0;
  }
  .search-result {
    padding: 8px 18px; cursor: pointer;
    border-left: 3px solid transparent;
    display: flex; flex-direction: column; gap: 2px;
  }
  .search-result.active {
    border-left-color: var(--accent);
    background: var(--bg-elevated);
  }
  .search-result .sr-name {
    font-family: var(--font-mono); font-size: 14px;
    color: var(--text-primary);
  }
  .search-result .sr-path {
    font-family: var(--font-mono); font-size: 11px;
    color: var(--text-tertiary);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .search-empty {
    padding: 20px 18px; color: var(--text-tertiary);
    font-family: var(--font-mono); font-size: 13px;
  }

  /* Navigation rails — conversation minimap & markdown TOC (desktop only, a quiet study aid) */
  .nav-rail {
    position: fixed; right: 16px; top: 80px;
    max-height: calc(100vh - 120px); overflow-y: auto;
    width: 200px; padding: 4px 0;
    z-index: 50;
  }
  .nav-rail-item {
    display: block; box-sizing: border-box; width: 100%;
    font-family: var(--font-mono); font-size: 10px; line-height: 1.5;
    color: var(--text-tertiary); text-align: left; background: none;
    padding: 3px 8px; border-left: 2px solid transparent;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    cursor: pointer; text-decoration: none;
    transition: color 150ms ease, border-color 150ms ease;
  }
  .nav-rail-item:hover { color: var(--text-secondary); text-decoration: none; }
  .nav-rail-item.active { color: var(--accent); border-left-color: var(--accent); }
  @media (max-width: 1099px) { .nav-rail { display: none; } }

  /* Keyboard navigation focus + shortcuts overlay */
  .listing tr.kb-focus td { background: var(--bg-elevated); border-left-color: var(--accent); }
  .listing tr.kb-focus .icon { color: var(--accent); }
  .conv-row.kb-focus { background: var(--bg-elevated); box-shadow: inset 3px 0 0 var(--accent); }
  .task-card.kb-focus { background: var(--bg-elevated); border-left-color: var(--accent); }
  .kb-overlay {
    position: fixed; inset: 0; z-index: 1000;
    display: none; align-items: center; justify-content: center;
    background: rgba(28, 25, 23, 0.72);
  }
  .kb-overlay.open { display: flex; }
  .kb-overlay-panel {
    background: var(--bg-surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 28px 32px; min-width: 380px; max-width: 90vw; max-height: 82vh; overflow-y: auto;
  }
  .kb-overlay-title {
    font-family: var(--font-mono); font-size: 13px; letter-spacing: 0.04em;
    text-transform: uppercase; color: var(--text-secondary);
    margin: 0 0 18px; padding-bottom: 10px; border-bottom: 1px solid var(--border-subtle);
  }
  .kb-overlay-grid {
    display: grid; grid-template-columns: auto 1fr; gap: 10px 20px; align-items: baseline;
  }
  .kb-overlay-key {
    font-family: var(--font-mono); font-size: 13px; color: var(--accent);
    white-space: nowrap; text-align: right;
  }
  .kb-overlay-desc {
    font-family: var(--font-mono); font-size: 13px; color: var(--text-secondary);
  }

  /* ---- shared small controls (used by the Models page) ---- */
  .steer-btn {
    background: none; border: 1px solid var(--border); border-radius: 3px; cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: .14em; text-transform: uppercase;
    color: var(--text-secondary); padding: 4px 12px;
    transition: color 150ms ease, border-color 150ms ease;
  }
  .steer-btn:hover { color: var(--accent); border-color: var(--accent); }
  .steer-link {
    background: none; border: none; cursor: pointer; font-family: var(--font-mono);
    font-size: 10px; letter-spacing: .1em; color: var(--text-tertiary); padding: 0;
    margin-left: 10px; transition: color 150ms ease;
  }
  .steer-link:hover { color: var(--accent); }
  .steer-note {
    font-family: var(--font-mono); font-size: 10px; color: var(--text-tertiary);
    margin: 12px 0 4px; letter-spacing: .04em;
  }
  .health-empty { font-family: var(--font-mono); font-size: 12.5px;
    color: var(--text-tertiary); padding: 14px 0; }

  /* ---- Models: which model answers in which channel ---- */
  .models-page { max-width: 820px; padding: 8px 40px 60px; --models-cols: 208px 1fr 168px; }  /* name · model · effort; px so the 11px header and the rows share one grid */
  .models-page h1 { font-family: Literata, serif; font-size: 28px; font-weight: 600; margin: 0 0 6px; }
  .models-page .subtitle { font-family: var(--font-mono); font-size: 12px;
    color: var(--text-tertiary); margin-bottom: 30px; line-height: 1.9; }
  .models-section { margin-bottom: 44px; }
  .models-section.default { margin-bottom: 30px; }
  .models-section-label { font-family: var(--font-mono); font-size: 11px;
    letter-spacing: .08em; text-transform: uppercase; color: var(--text-tertiary);
    padding-bottom: 10px; border-bottom: 1px solid var(--border-subtle); margin-bottom: 4px;
    display: flex; justify-content: space-between; align-items: baseline; gap: 16px; }
  .models-section-label .hint { text-transform: none; letter-spacing: 0; font-size: 11px; text-align: right; }
  /* column labels sit over the columns they name — same grid as the rows */
  .models-section-label.cols { display: grid; grid-template-columns: var(--models-cols); gap: 14px; }
  .models-section-label.cols .col { text-transform: none; letter-spacing: 0; }
  .models-row { display: grid; grid-template-columns: var(--models-cols); align-items: center;
    gap: 14px; padding: 8px 0; border-bottom: 1px solid var(--border-subtle); }
  .models-name { font-family: var(--font-mono); font-size: 12.5px;
    color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .models-name .note { font-size: 11px; color: var(--text-tertiary); }
  /* the default row: model is read-only text (it lives in settings.json; the reason is printed inline), effort is a real dropdown */
  .models-row.default .fixed { font-family: var(--font-mono); font-size: 12.5px; color: var(--text-primary);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .models-row.default .fixed .why { font-size: 11px; color: var(--text-tertiary); white-space: normal; line-height: 1.6; margin-top: 3px; }
  .models-page select, .models-page input[type=text] {
    background: var(--bg-surface); color: var(--text-primary); border: 1px solid var(--border);
    border-radius: 3px; font-family: var(--font-mono); font-size: 12.5px;
    padding: 5px 8px; width: 100%; box-sizing: border-box; }
  .models-page select:focus, .models-page input[type=text]:focus, .models-page textarea:focus {
    outline: none; border-color: var(--accent); }
  .models-page select.inherit { color: var(--text-tertiary); font-style: italic; }
  .models-saved { font-family: var(--font-mono); font-size: 10px; letter-spacing: .1em;
    text-transform: uppercase; color: var(--text-tertiary); text-align: right; opacity: 0;
    transition: opacity 400ms ease; }
  .models-saved.show { opacity: 1; color: var(--status-green); }
  .models-saved.err { opacity: 1; color: #DE7452; text-transform: none; letter-spacing: 0; }
  /* one save-status line for the whole page, stuck to the bottom of the view — rows don't reserve a column for it */
  .models-status { position: sticky; bottom: 0; padding: 8px 0; background: var(--bg-primary); }
  /* the add-a-model box is the last row of the model list */
  .models-add { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; padding: 12px 0 10px; }
  .models-prompt { padding: 14px 0 18px; border-bottom: 1px solid var(--border-subtle); }
  .models-prompt-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 8px; }
  .models-prompt-head .model { font-family: var(--font-mono); font-size: 12.5px; color: var(--text-primary); }
  .models-prompt-head .where { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); text-align: right; line-height: 1.8; }
  .models-prompt textarea { width: 100%; box-sizing: border-box; min-height: 96px; resize: vertical;
    background: var(--bg-sidebar); color: var(--text-primary); border: 1px solid var(--border-subtle);
    border-radius: 3px; font-family: Literata, serif; font-size: 14.5px; line-height: 1.6; padding: 10px 12px; }
  .models-prompt textarea::placeholder { color: var(--text-tertiary); font-family: var(--font-mono); font-size: 11.5px; }
  .models-prompt-foot { display: flex; align-items: center; gap: 12px; margin-top: 6px; }
  .models-prompt-foot .steer-link { margin-left: 0; }
  /* text links in the prompt section must not read as captions next to the grey where-used label */
  .models-page .steer-link { font-size: 11px; letter-spacing: 0; color: var(--text-secondary);
    text-decoration: underline dotted; text-underline-offset: 3px; }
  .models-page .steer-link:hover { color: var(--accent); }
  .models-foot { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); margin-top: 8px; }
  .models-foot a { color: var(--text-secondary); }
  .models-foot a:hover { color: var(--accent); }
  @media (max-width: 720px) {
    .models-page { padding: 8px 20px 60px; }
    .models-section-label.cols { display: flex; }
    .models-section-label.cols .col { display: none; }
    .models-row { grid-template-columns: 1fr 1fr; }
    .models-name, .models-row.default .fixed { grid-column: 1 / -1; }
  }
</style>
</head>
<body>
<button class="hamburger" id="hamburger-btn">&#9776;</button>
<div class="sidebar-overlay" id="sidebar-overlay"></div>
<div class="sidebar" id="sidebar">
  <hr class="sidebar-rule">
  SIDEBAR_LINKS
</div>
<div class="main">
  <div class="breadcrumb">BREADCRUMB</div>
  CONTENT
</div>
<div id="search-palette">
  <div class="search-box">
    <input id="search-input" type="text" autocomplete="off" spellcheck="false"
           placeholder="Jump to a file or folder...">
    <ul id="search-results"></ul>
  </div>
</div>
<script>
// Sidebar toggle for mobile
const hamburger = document.getElementById('hamburger-btn');
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebar-overlay');
function toggleSidebar() {
  sidebar.classList.toggle('open');
  overlay.classList.toggle('open');
}
hamburger.addEventListener('click', toggleSidebar);
overlay.addEventListener('click', toggleSidebar);
// Close sidebar when clicking a link (mobile)
sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
  sidebar.classList.remove('open');
  overlay.classList.remove('open');
}));

// Render markdown content if present
const mdEl = document.getElementById('markdown-raw');
if (mdEl) {
  const raw = mdEl.textContent;
  const rendered = marked.parse(raw);
  document.getElementById('markdown-rendered').innerHTML = rendered;
  // Apply syntax highlighting to code blocks
  document.querySelectorAll('#markdown-rendered pre code').forEach(el => hljs.highlightElement(el));
}
// Apply syntax highlighting to code files
document.querySelectorAll('.code-body pre code').forEach(el => hljs.highlightElement(el));

// Edit functionality for CLAUDE.md — CodeMirror 5
const editBtn = document.getElementById('btn-edit');
if (editBtn) {
  const filePath = editBtn.dataset.path;
  const rendered = document.getElementById('markdown-rendered');
  const rawEl = document.getElementById('markdown-raw');
  const editArea = document.getElementById('edit-area');
  const cmContainer = document.getElementById('cm-editor');
  const saveBtn = document.getElementById('btn-save');
  const cancelBtn = document.getElementById('btn-cancel');
  const status = document.getElementById('save-status');
  const conflictWarning = document.getElementById('conflict-warning');
  const overwriteBtn = document.getElementById('btn-overwrite');
  const reloadBtn = document.getElementById('btn-reload');
  let cmEditor = null;
  let dirty = false;       // unsaved changes in the editor
  let editing = false;     // edit mode active
  let expectedMtime = editBtn.dataset.mtime ? parseFloat(editBtn.dataset.mtime) : null;

  function setDirty(v) {
    dirty = v;
    if (v) conflictWarning.style.display = 'none';
  }

  // Warn before leaving with unsaved changes.
  window.addEventListener('beforeunload', function(e) {
    if (editing && dirty) {
      e.preventDefault();
      e.returnValue = '';
      return '';
    }
  });

  // force = re-POST without expected_mtime (overwrite anyway).
  function doSave(force) {
    if (!cmEditor) return;
    const content = cmEditor.getValue();
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    conflictWarning.style.display = 'none';
    const body = {path: filePath, content: content};
    if (!force && expectedMtime !== null) body.expected_mtime = expectedMtime;
    fetch('/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    }).then(r => r.json().then(result => ({status: r.status, result}))).then(({status: httpStatus, result}) => {
      if (result.ok) {
        if (typeof result.mtime === 'number') expectedMtime = result.mtime;
        setDirty(false);
        status.textContent = 'Saved!';
        status.style.display = 'inline';
        status.style.color = 'var(--status-green)';
        rendered.innerHTML = marked.parse(content);
        rendered.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
        rawEl.textContent = content;
        setTimeout(() => {
          editArea.style.display = 'none';
          rendered.style.display = 'block';
          editBtn.style.display = 'inline-block';
          status.style.display = 'none';
          editing = false;
        }, 800);
      } else if (httpStatus === 409 || result.conflict) {
        // Surface conflict inline in the edit bar (no browser alert).
        if (typeof result.current_mtime === 'number') expectedMtime = result.current_mtime;
        conflictWarning.style.display = 'inline-flex';
      } else {
        status.textContent = 'Error: ' + result.error;
        status.style.color = '#BF616A';
        status.style.display = 'inline';
      }
    }).catch(e => {
      status.textContent = 'Error: ' + e.message;
      status.style.color = '#BF616A';
      status.style.display = 'inline';
    }).finally(() => {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save';
    });
  }

  editBtn.addEventListener('click', () => {
    rendered.style.display = 'none';
    editArea.style.display = 'block';
    editBtn.style.display = 'none';
    editing = true;
    setDirty(false);
    conflictWarning.style.display = 'none';

    if (!cmEditor) {
      cmEditor = CodeMirror(cmContainer, {
        value: rawEl.textContent,
        mode: 'markdown',
        lineNumbers: true,
        lineWrapping: true,
        styleActiveLine: true,
        matchBrackets: true,
        indentUnit: 2,
        tabSize: 2,
        indentWithTabs: false,
        extraKeys: {
          'Cmd-S': function() { doSave(false); },
          'Ctrl-S': function() { doSave(false); },
          'Enter': 'newlineAndIndentContinueMarkdownList',
        },
      });
      cmEditor.on('change', () => { setDirty(true); });
    } else {
      cmEditor.setValue(rawEl.textContent);
      setDirty(false);
    }
    setTimeout(() => { cmEditor.refresh(); cmEditor.focus(); }, 10);
  });

  cancelBtn.addEventListener('click', () => {
    if (dirty && !confirm('Discard unsaved changes?')) return;
    editArea.style.display = 'none';
    rendered.style.display = 'block';
    editBtn.style.display = 'inline-block';
    conflictWarning.style.display = 'none';
    editing = false;
    setDirty(false);
  });

  overwriteBtn.addEventListener('click', () => { doSave(true); });
  reloadBtn.addEventListener('click', () => {
    if (dirty && !confirm('Discard unsaved changes?')) return;
    location.reload();
  });

  saveBtn.addEventListener('click', () => doSave(false));
}

// --- Directory listing: filter + sort ---
(function() {
  var controls = document.querySelector('.listing-controls');
  var table = document.querySelector('.listing table');
  if (!controls || !table) return;

  var tbody = table.querySelector('tbody');
  var input = controls.querySelector('.listing-filter');
  var countEl = controls.querySelector('.listing-count');
  var sortBtns = controls.querySelectorAll('.sort-btn');
  var dirKey = controls.getAttribute('data-dirkey') || '';
  var storeKey = 'fe-sort:' + dirKey;

  var ARROW_UP = '↑', ARROW_DOWN = '↓';
  var sortKey = 'name', sortDir = 1;  // 1 = asc, -1 = desc; default name ascending

  function rows() { return Array.prototype.slice.call(tbody.querySelectorAll('tr')); }

  function valFor(tr, key) {
    if (key === 'size') return parseFloat(tr.getAttribute('data-size')) || 0;
    if (key === 'modified') return parseFloat(tr.getAttribute('data-mtime')) || 0;
    return (tr.getAttribute('data-name') || '').toLowerCase();
  }

  function applySort() {
    var rs = rows();
    rs.sort(function(a, b) {
      // Dirs always grouped first
      var ad = a.getAttribute('data-isdir') === '1' ? 0 : 1;
      var bd = b.getAttribute('data-isdir') === '1' ? 0 : 1;
      if (ad !== bd) return ad - bd;
      var av = valFor(a, sortKey), bv = valFor(b, sortKey);
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
    rs.forEach(function(tr) { tbody.appendChild(tr); });
    sortBtns.forEach(function(btn) {
      var k = btn.getAttribute('data-key');
      if (k === sortKey) {
        btn.classList.add('active');
        btn.textContent = k + ' ' + (sortDir === 1 ? ARROW_UP : ARROW_DOWN);
      } else {
        btn.classList.remove('active');
        btn.textContent = k;
      }
    });
  }

  function applyFilter() {
    var q = input.value.trim().toLowerCase();
    var rs = rows(), shown = 0;
    rs.forEach(function(tr) {
      var name = (tr.getAttribute('data-name') || '').toLowerCase();
      var match = !q || name.indexOf(q) !== -1;
      tr.style.display = match ? '' : 'none';
      if (match) shown++;
    });
    countEl.textContent = q ? (shown + ' of ' + rs.length) : '';
  }

  sortBtns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      var k = btn.getAttribute('data-key');
      if (k === sortKey) { sortDir = -sortDir; }
      else { sortKey = k; sortDir = 1; }
      try { localStorage.setItem(storeKey, JSON.stringify({ key: sortKey, dir: sortDir })); } catch (e) {}
      applySort();
    });
  });

  input.addEventListener('input', applyFilter);
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { input.value = ''; applyFilter(); input.blur(); }
  });

  // Restore last sort for this directory
  try {
    var saved = JSON.parse(localStorage.getItem(storeKey) || 'null');
    if (saved && saved.key) { sortKey = saved.key; sortDir = saved.dir === -1 ? -1 : 1; }
  } catch (e) {}

  applySort();
})();

// --- Global keyboard navigation ---
(function() {
  var OVERLAY_ID = 'kb-shortcuts-overlay';
  var HOME = 'HOME_BROWSE_PATH_PLACEHOLDER';

  function isTyping(t) {
    if (!t) return false;
    var tag = (t.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if (t.isContentEditable) return true;
    if (t.closest && t.closest('.CodeMirror')) return true;
    return false;
  }

  function rows() {
    return Array.prototype.slice.call(
      document.querySelectorAll('.listing tr, .conv-row, .task-card')
    );
  }

  var idx = -1;

  function clearFocus() {
    var cur = document.querySelectorAll('.kb-focus');
    for (var i = 0; i < cur.length; i++) cur[i].classList.remove('kb-focus');
  }

  function focusRow(i) {
    var r = rows();
    if (!r.length) return;
    if (i < 0) i = 0;
    if (i >= r.length) i = r.length - 1;
    idx = i;
    clearFocus();
    var el = r[idx];
    el.classList.add('kb-focus');
    el.scrollIntoView({ block: 'nearest' });
  }

  function move(delta) {
    var r = rows();
    if (!r.length) return;
    if (idx < 0) { focusRow(delta > 0 ? 0 : r.length - 1); return; }
    focusRow(idx + delta);
  }

  function openFocused() {
    var r = rows();
    if (idx < 0 || idx >= r.length) return;
    var el = r[idx];
    if (el.classList.contains('conv-row')) {
      if (typeof el.onclick === 'function') el.onclick();
      return;
    }
    if (el.classList.contains('task-card')) {
      var a = el.closest('a');
      if (a && a.href) window.location = a.href;
      return;
    }
    var link = el.querySelector('.name a');
    if (link && link.href) window.location = link.href;
  }

  function goUp() {
    var p = location.pathname;
    if (p.indexOf('/conversations/') === 0) { window.location = '/conversations'; return; }
    if (p.indexOf('/tasks/') === 0) { window.location = '/tasks'; return; }
    if (p.indexOf('/browse') === 0) {
      var parts = p.replace(/\/+$/, '').split('/');
      parts.pop();
      var up = parts.join('/');
      if (up.length < HOME.length) up = HOME;
      window.location = up;
    }
  }

  function overlay() { return document.getElementById(OVERLAY_ID); }

  function buildOverlay() {
    var el = overlay();
    if (el) return el;
    var binds = [
      ['j / k', 'Move focus down / up'],
      ['Enter', 'Open focused row'],
      ['h / Backspace', 'Up a directory / back'],
      ['g h', 'Go home'],
      ['g t', 'Go to tasks'],
      ['g c', 'Go to conversations'],
      ['g d', 'Go to diary'],
      ['?', 'Toggle this help'],
      ['Esc', 'Close this help']
    ];
    var grid = '';
    for (var i = 0; i < binds.length; i++) {
      grid += '<div class="kb-overlay-key">' + binds[i][0] +
              '</div><div class="kb-overlay-desc">' + binds[i][1] + '</div>';
    }
    el = document.createElement('div');
    el.id = OVERLAY_ID;
    el.className = 'kb-overlay';
    el.innerHTML = '<div class="kb-overlay-panel">' +
      '<p class="kb-overlay-title">Keyboard shortcuts</p>' +
      '<div class="kb-overlay-grid">' + grid + '</div></div>';
    el.addEventListener('click', function(e) { if (e.target === el) closeOverlay(); });
    document.body.appendChild(el);
    return el;
  }

  function toggleOverlay() { buildOverlay().classList.toggle('open'); }
  function closeOverlay() { var el = overlay(); if (el) el.classList.remove('open'); }
  function overlayOpen() { var el = overlay(); return !!(el && el.classList.contains('open')); }

  var gPending = false, gTimer = null;
  function clearG() { gPending = false; if (gTimer) { clearTimeout(gTimer); gTimer = null; } }

  document.addEventListener('keydown', function(e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (isTyping(e.target)) return;

    var k = e.key;

    if (k === 'Escape') {
      if (overlayOpen()) { e.preventDefault(); closeOverlay(); }
      clearG();
      return;
    }

    if (overlayOpen()) {
      if (k === '?') { e.preventDefault(); closeOverlay(); }
      return;
    }

    if (gPending) {
      clearG();
      if (k === 'h') { e.preventDefault(); window.location = HOME; return; }
      if (k === 't') { e.preventDefault(); window.location = '/tasks'; return; }
      if (k === 'c') { e.preventDefault(); window.location = '/conversations'; return; }
      if (k === 'd') { e.preventDefault(); window.location = HOME + '/diary'; return; }
      return;
    }

    if (k === 'g') { gPending = true; gTimer = setTimeout(clearG, 600); return; }
    if (k === 'j') { e.preventDefault(); move(1); return; }
    if (k === 'k') { e.preventDefault(); move(-1); return; }
    if (k === 'Enter') { if (idx >= 0) { e.preventDefault(); openFocused(); } return; }
    if (k === 'h' || k === 'Backspace') { e.preventDefault(); goUp(); return; }
    if (k === '?') { e.preventDefault(); toggleOverlay(); return; }
  });
})();

// --- Navigation rail: conversation minimap (right side, desktop) ---
// Lists every real USER turn; scroll-spy highlights the topmost in view.
// Built from the DOM and observes the container so late-appended turns join the rail.
(function() {
  var container = document.querySelector('.conv-detail');
  if (!container) return;
  var rail = null;
  var entries = [];

  function ensureRail() {
    if (rail) return;
    rail = document.createElement('nav');
    rail.className = 'nav-rail';
    rail.setAttribute('aria-label', 'Conversation minimap');
    document.body.appendChild(rail);
  }

  function addEntry(msgEl) {
    if (msgEl._railAdded) return;
    if (msgEl.classList.contains('conv-meta-msg')) return;
    var md = msgEl.querySelector('.conv-markdown');
    var txt = md ? (md.textContent || '').trim() : '';
    if (!txt) return; // skip tool-result-only turns
    msgEl._railAdded = true;
    if (!msgEl.id) msgEl.id = 'conv-turn-' + entries.length;
    ensureRail();
    var a = document.createElement('a');
    a.className = 'nav-rail-item';
    a.href = '#' + msgEl.id;
    a.textContent = txt.length > 50 ? txt.slice(0, 50) + '…' : txt;
    a.title = txt.slice(0, 200);
    a.addEventListener('click', function(e) {
      e.preventDefault();
      msgEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    rail.appendChild(a);
    entries.push({ a: a, msgEl: msgEl });
  }

  function scan() {
    var turns = document.querySelectorAll('.conv-message.role-user:not(.conv-meta-msg)');
    for (var i = 0; i < turns.length; i++) addEntry(turns[i]);
    if (rail) rail.style.display = entries.length < 3 ? 'none' : '';
  }

  function onScroll() {
    if (!rail || entries.length < 3) return;
    var best = 0, bestTop = -Infinity;
    for (var i = 0; i < entries.length; i++) {
      var top = entries[i].msgEl.getBoundingClientRect().top;
      if (top <= 120 && top > bestTop) { bestTop = top; best = i; }
    }
    for (var j = 0; j < entries.length; j++) {
      entries[j].a.classList.toggle('active', j === best);
    }
  }

  scan();
  var obs = new MutationObserver(function() { scan(); });
  obs.observe(container, { childList: true, subtree: true });
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// --- Navigation rail: markdown table of contents (right side, desktop) ---
// Built from h1/h2/h3 after marked.parse; only for long, heading-rich docs.
(function() {
  var el = document.getElementById('markdown-rendered');
  if (!el) return;
  var headings = el.querySelectorAll('h1, h2, h3');
  if (headings.length < 4) return;
  if (el.scrollHeight < window.innerHeight * 1.5) return;

  var rail = document.createElement('nav');
  rail.className = 'nav-rail';
  rail.setAttribute('aria-label', 'Table of contents');
  var items = [];

  Array.prototype.forEach.call(headings, function(h, idx) {
    if (!h.id) {
      var slug = (h.textContent || '').trim().toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '').replace(/\s+/g, '-').slice(0, 60);
      h.id = 'toc-' + (slug || 'h') + '-' + idx;
    }
    var level = parseInt(h.tagName.charAt(1), 10);
    var a = document.createElement('a');
    a.className = 'nav-rail-item';
    a.href = '#' + h.id;
    a.textContent = (h.textContent || '').trim();
    a.title = a.textContent;
    a.style.paddingLeft = (8 + (level - 1) * 10) + 'px';
    a.addEventListener('click', function(e) {
      e.preventDefault();
      h.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    rail.appendChild(a);
    items.push({ a: a, h: h });
  });

  document.body.appendChild(rail);

  function onScroll() {
    var best = 0, bestTop = -Infinity;
    for (var i = 0; i < items.length; i++) {
      var top = items[i].h.getBoundingClientRect().top;
      if (top <= 120 && top > bestTop) { bestTop = top; best = i; }
    }
    for (var j = 0; j < items.length; j++) {
      items[j].a.classList.toggle('active', j === best);
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// --- Cmd+K search palette ---
(function() {
  var palette = document.getElementById('search-palette');
  var input = document.getElementById('search-input');
  var resultsEl = document.getElementById('search-results');
  if (!palette || !input || !resultsEl) return;
  var results = [];
  var active = -1;
  var debounceTimer = null;

  function isTypingContext(el) {
    if (!el) return false;
    var tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return true;
    if (el.isContentEditable) return true;
    if (el.closest && el.closest('.CodeMirror')) return true;
    return false;
  }

  function openPalette() {
    palette.classList.add('open');
    input.value = '';
    results = [];
    active = -1;
    resultsEl.innerHTML = '';
    input.focus();
  }

  function closePalette() {
    palette.classList.remove('open');
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
  }

  function render() {
    if (results.length === 0) {
      resultsEl.innerHTML = '<li class="search-empty">No matches</li>';
      return;
    }
    var frag = document.createDocumentFragment();
    results.forEach(function(r, i) {
      var li = document.createElement('li');
      li.className = 'search-result' + (i === active ? ' active' : '');
      var name = document.createElement('div');
      name.className = 'sr-name';
      name.textContent = r.name + (r.is_dir ? '/' : '');
      var pathEl = document.createElement('div');
      pathEl.className = 'sr-path';
      var parent = r.path.replace(/\/[^\/]*$/, '') || '/';
      pathEl.textContent = parent;
      li.appendChild(name);
      li.appendChild(pathEl);
      li.addEventListener('mouseenter', function() { active = i; updateActive(); });
      li.addEventListener('click', function() { navigate(r); });
      frag.appendChild(li);
    });
    resultsEl.innerHTML = '';
    resultsEl.appendChild(frag);
  }

  function updateActive() {
    var rows = resultsEl.querySelectorAll('.search-result');
    rows.forEach(function(row, i) {
      row.classList.toggle('active', i === active);
      if (i === active) row.scrollIntoView({ block: 'nearest' });
    });
  }

  function navigate(r) {
    if (!r) return;
    window.location.href = '/browse' + r.path;
  }

  function doSearch(q) {
    if (!q) { results = []; active = -1; resultsEl.innerHTML = ''; return; }
    fetch('/api/search?q=' + encodeURIComponent(q))
      .then(function(resp) { return resp.json(); })
      .then(function(data) {
        results = data || [];
        active = results.length ? 0 : -1;
        render();
      })
      .catch(function() { results = []; active = -1; render(); });
  }

  input.addEventListener('input', function() {
    var q = input.value.trim();
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function() { doSearch(q); }, 150);
  });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (results.length) { active = (active + 1) % results.length; updateActive(); }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (results.length) { active = (active - 1 + results.length) % results.length; updateActive(); }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (active >= 0 && results[active]) navigate(results[active]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closePalette();
    }
  });

  palette.addEventListener('mousedown', function(e) {
    if (e.target === palette) closePalette();
  });

  document.addEventListener('keydown', function(e) {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      if (palette.classList.contains('open')) { closePalette(); return; }
      if (isTypingContext(document.activeElement)) return;
      e.preventDefault();
      openPalette();
    }
  });
})();

</script>
</body>
</html>"""


def human_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def human_date(ts):
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%b %d, %Y %H:%M")


def make_sidebar(current_path='', visitor=None):
    visitor = visitor or get_visitor()
    ring = visitor["ring"]
    bookmarks = get_bookmarks_for_ring(ring)

    links = []
    for name, path in bookmarks:
        icon_svg = SIDEBAR_ICONS.get(name, SIDEBAR_ICONS['Home'])
        active = ''
        if current_path and current_path.startswith(path):
            active = ' active'
        links.append(f'<a href="/browse{path}" class="{active}"><span class="icon">{icon_svg}</span>{name}</a>')

    # CLAUDE.md link
    claude_md_path = str(BASE_DIR / 'CLAUDE.md')
    claude_active = ' active' if current_path == claude_md_path else ''
    claude_icon = SIDEBAR_ICONS['CLAUDE.md']
    links.append(f'<a href="/browse{claude_md_path}" class="{claude_active}"><span class="icon">{claude_icon}</span>CLAUDE.md</a>')

    # Scheduled Tasks link — ring 1 only (system internals)
    if TASK_PREFIXES and ring <= 1:
        tasks_active = ' active' if current_path == 'Scheduled Tasks' or current_path.startswith('Task:') else ''
        tasks_icon = SIDEBAR_ICONS['Scheduled Tasks']
        links.append(f'<a href="/tasks" class="{tasks_active}"><span class="icon">{tasks_icon}</span>Scheduled Tasks</a>')

    # Conversations link — ring 1 only (session logs)
    if ring <= 1:
        conv_active = ' active' if current_path == 'Conversations' or current_path.startswith('Conversation:') else ''
        conv_icon = SIDEBAR_ICONS['Conversations']
        links.append(f'<a href="/conversations" class="{conv_active}"><span class="icon">{conv_icon}</span>Conversations</a>')

    # Models link — ring 1 only (edits the Slack bot's config)
    if ring <= 1:
        models_active = ' active' if current_path == 'Models' else ''
        links.append(f'<a href="/models" class="{models_active}"><span class="icon">{SIDEBAR_ICONS["Models"]}</span>Models</a>')

    return "\n".join(links)


def make_breadcrumb(path):
    parts = Path(path).parts
    crumbs = []
    for i, part in enumerate(parts):
        full = "/".join(parts[:i+1])
        if not full.startswith("/"):
            full = "/" + full
        crumbs.append(f'<a href="/browse{full}">{part}</a>')
    return ' <span class="sep">/</span> '.join(crumbs)


def lang_for_ext(ext):
    mapping = {
        '.py': 'python', '.rb': 'ruby', '.js': 'javascript', '.ts': 'typescript',
        '.jsx': 'javascript', '.tsx': 'typescript', '.json': 'json', '.yml': 'yaml',
        '.yaml': 'yaml', '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
        '.css': 'css', '.html': 'html', '.sql': 'sql', '.rs': 'rust',
        '.go': 'go', '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.swift': 'swift',
        '.toml': 'toml', '.xml': 'xml', '.erb': 'erb',
    }
    return mapping.get(ext, '')


def _file_icon_svg(name):
    """Return an SVG icon for a file based on its extension."""
    ext = Path(name).suffix.lower().lstrip('.')
    return FILE_TYPE_SVGS.get(ext, FILE_TYPE_SVGS['_default'])


def _page_title(path_label):
    """Compute the browser tab title from a _render_page label.

    Filesystem paths -> "<basename> — <parent>" (or "Home" for BASE_DIR).
    Tasks/Conversations labels get friendly names. Everything gets the
    configured DISPLAY_NAME suffix.
    """
    if path_label.startswith('/'):
        p = Path(path_label)
        if str(p) == str(BASE_DIR):
            title = 'Home'
        else:
            parent = p.parent.name or '/'
            title = f'{p.name} — {parent}'
    elif path_label == 'Scheduled Tasks':
        title = 'Tasks'
    elif path_label.startswith('Task: '):
        title = f'{path_label[len("Task: "):]} — Tasks'
    elif path_label == 'Conversations':
        title = 'Conversations'
    elif path_label.startswith('Conversation: '):
        title = f'{path_label[len("Conversation: "):]} — Conversations'
    elif path_label == 'Models':
        title = 'Models'
    else:
        title = path_label
    return html_mod.escape(f'{title} · {DISPLAY_NAME}')


def _render_page(path_label, content, visitor=None):
    """Wrap content in the full HTML template with sidebar and breadcrumb."""
    visitor = visitor or get_visitor()
    page = HTML_TEMPLATE.replace('PAGE_TITLE', _page_title(path_label))
    page = page.replace('HOME_BROWSE_PATH_PLACEHOLDER', f'/browse{BASE_DIR}')
    page = page.replace('SIDEBAR_LINKS', make_sidebar(path_label, visitor))
    page = page.replace('BREADCRUMB', make_breadcrumb(path_label))
    page = page.replace('CONTENT', content)
    return Response(page, content_type='text/html; charset=utf-8')


def _home_hero():
    """Return hero HTML for the home page."""
    script_dir = Path(__file__).parent
    hero_img = script_dir / 'hero.png'
    if not hero_img.exists():
        hero_img = script_dir / 'hero.jpg'
    if hero_img.exists():
        return f'''<div class="hero-section">
            <img src="/raw{hero_img}" alt="{DISPLAY_NAME}">
        </div>'''
    now = datetime.now()
    hour = now.hour
    if hour < 12:
        greeting = 'Good morning'
    elif hour < 17:
        greeting = 'Good afternoon'
    else:
        greeting = 'Good evening'
    return f'''<div class="hero-section" style="text-align:left; padding-bottom:16px; border-bottom:1px solid var(--border-subtle); margin-bottom:8px;">
        <div style="font-family:var(--font-prose); font-size:20px; color:var(--accent); margin-bottom:4px;">{greeting}.</div>
        <div style="font-family:var(--font-prose); font-size:14px; color:var(--text-secondary);">Welcome to {DISPLAY_NAME}\'s workspace.</div>
    </div>'''


# ============================================================
# CONVERSATION LOG HELPERS
# ============================================================

# Conversations directory: first session dir found under .claude/projects
CONVERSATIONS_DIR = None
for _d in _get_session_dirs():
    CONVERSATIONS_DIR = _d
    break
if CONVERSATIONS_DIR is None:
    CONVERSATIONS_DIR = Path.home() / '.claude' / 'projects'

# --- Session metadata cache ---------------------------------------------
# Parsing every .jsonl on each /conversations load is slow (1,000+ files,
# some tens of MB). Cache each file's parsed metadata keyed by path, and only
# re-parse files whose (mtime, size) changed or that are new. The cache is
# guarded by a lock (Waitress runs 8 threads) and persisted to ~/.cache so a
# server restart doesn't re-parse everything.
_SESSIONS_CACHE = {}          # path(str) -> {'mtime', 'size', 'meta'}
_SESSIONS_CACHE_LOCK = threading.Lock()
_SESSIONS_CACHE_LOADED = False
SESSIONS_CACHE_FILE = Path.home() / '.cache' / 'file-explorer-sessions.json'


_SCHEDULED_PREFIX_CACHE = None


def _scheduled_prompt_prefixes():
    """Leading literal text (pre-variable) of each scheduled-task claude prompt.

    Derived generically from the shell scripts referenced by the launchd plists
    this app already monitors (get_launchd_jobs -> extract_claude_prompt), so it
    stays owner-agnostic. Cached at module level; used to flag cron/scheduled
    sessions cheaply. Empty when no tasks are configured
    (FILE_EXPLORER_TASK_PREFIXES unset)."""
    global _SCHEDULED_PREFIX_CACHE
    if _SCHEDULED_PREFIX_CACHE is not None:
        return _SCHEDULED_PREFIX_CACHE
    prefixes = []
    try:
        for job in get_launchd_jobs():
            script = job.get('script')
            if not script:
                continue
            prompt = extract_claude_prompt(script)
            if not prompt:
                continue
            lead = re.split(r'\$\{?\w+\}?', prompt)[0]
            lead = lead.replace('\\n', ' ').replace('\n', ' ').strip()[:40]
            if len(lead) >= 25:
                prefixes.append(lead)
    except Exception:
        pass
    _SCHEDULED_PREFIX_CACHE = prefixes
    return prefixes


# Generic Slack forwarding patterns (owner-agnostic).
_SLACK_DM_RE = re.compile(r'^\[[^\]]+\]\(U[A-Z0-9]+\):')
_SLACK_CHANNEL_RE = re.compile(r'(?:public |private )?channel #([A-Za-z0-9_-]+)')


def _classify_session_source(first_user_msg):
    """Classify a session by its RAW first user message (before preview stripping).
    Returns (kind, source) where kind is channel|dm|scheduled|terminal."""
    if not first_user_msg:
        return 'terminal', 'Terminal'
    m = first_user_msg.lstrip()
    ch = _SLACK_CHANNEL_RE.search(m[:120])
    if ch:
        return 'channel', '#' + ch.group(1)
    if m.startswith('You received this message') or _SLACK_DM_RE.match(m):
        return 'dm', 'DM'
    norm = m.replace('\n', ' ')[:50]
    for key in _scheduled_prompt_prefixes():
        if norm.startswith(key) or key.startswith(norm[:40]):
            return 'scheduled', 'Scheduled'
    return 'terminal', 'Terminal'


def _parse_session_file(f, stat):
    """Parse one JSONL session file into its metadata dict (no caching)."""
    size = stat.st_size
    mtime = stat.st_mtime

    # Efficient scan: read line by line, extract metadata without loading entire file
    first_user_msg = ''
    first_timestamp = None
    last_timestamp = None
    msg_count = 0
    user_count = 0
    assistant_count = 0
    entrypoint = ''

    with open(f) as fh:
        for line in fh:
            try:
                obj = json.loads(line)
                t = obj.get('type')
                ts = obj.get('timestamp')

                if t == 'user':
                    user_count += 1
                    msg_count += 1
                    if ts and not first_timestamp:
                        first_timestamp = ts
                    if ts:
                        last_timestamp = ts
                    if not entrypoint:
                        entrypoint = obj.get('entrypoint', '')
                    if not first_user_msg:
                        msg = obj.get('message', {})
                        content = msg.get('content', '')
                        if isinstance(content, str):
                            first_user_msg = content[:300]
                        elif isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get('type') == 'text':
                                    first_user_msg = c.get('text', '')[:300]
                                    break

                elif t == 'assistant':
                    assistant_count += 1
                    msg_count += 1
                    if ts:
                        last_timestamp = ts
            except (json.JSONDecodeError, KeyError):
                continue

    # Classify source from the RAW first message, before preview stripping
    kind, source = _classify_session_source(first_user_msg)

    # Clean up the preview - strip Slack forwarding prefix
    preview = first_user_msg
    slack_prefix = re.match(
        r'You received this message .+? respond with exactly: SKIP\s*',
        preview, re.DOTALL
    )
    if slack_prefix:
        preview = preview[slack_prefix.end():]
    if preview and len(preview) > 300:
        preview = preview[:300]
    preview = preview.strip().replace('\n', ' ')[:100]

    return {
        'id': f.stem,
        'path': str(f),
        'size': size,
        'mtime': mtime,
        'first_timestamp': first_timestamp,
        'last_timestamp': last_timestamp,
        'msg_count': msg_count,
        'user_count': user_count,
        'assistant_count': assistant_count,
        'preview': preview,
        'entrypoint': entrypoint,
        'kind': kind,
        'source': source,
    }


def _load_sessions_cache_from_disk():
    """Populate the in-memory cache from the persisted JSON file (best effort).

    Called once, under the cache lock. Corrupt/missing files are ignored so we
    simply fall back to a full parse.
    """
    global _SESSIONS_CACHE_LOADED
    if _SESSIONS_CACHE_LOADED:
        return
    _SESSIONS_CACHE_LOADED = True
    try:
        with open(SESSIONS_CACHE_FILE) as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            for path, entry in data.items():
                if (isinstance(entry, dict)
                        and 'mtime' in entry and 'size' in entry
                        and isinstance(entry.get('meta'), dict)):
                    _SESSIONS_CACHE[path] = entry
    except Exception:
        # Missing or corrupt cache — start empty, full parse will rebuild it.
        _SESSIONS_CACHE.clear()


def _write_sessions_cache_to_disk(snapshot):
    """Atomically persist a snapshot of the cache (temp file + rename)."""
    try:
        SESSIONS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(SESSIONS_CACHE_FILE.parent),
            prefix='.sessions-cache-', suffix='.tmp',
        )
        try:
            with os.fdopen(fd, 'w') as fh:
                json.dump(snapshot, fh)
            os.replace(tmp, SESSIONS_CACHE_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        # Persistence is best-effort; a failure here must not break the page.
        pass


def list_conversation_sessions():
    """List all JSONL conversation sessions with metadata.

    Backed by an in-memory (and disk-persisted) cache keyed by file path. Only
    files that are new or whose (mtime, size) changed are re-parsed; deleted
    files are evicted. Return contract is unchanged: same keys, sorted by mtime
    descending.
    """
    sessions = []
    if not CONVERSATIONS_DIR.exists():
        return sessions

    # Stat every file (cheap) outside the lock, and figure out which files
    # actually need a (slow) re-parse.
    current = {}   # path(str) -> (file, mtime, size)
    for f in CONVERSATIONS_DIR.glob('*.jsonl'):
        try:
            stat = f.stat()
        except OSError:
            continue
        current[str(f)] = (f, stat.st_mtime, stat.st_size)

    with _SESSIONS_CACHE_LOCK:
        _load_sessions_cache_from_disk()
        # Decide what needs parsing while holding the lock (cheap comparisons).
        to_parse = []
        for path, (f, mtime, size) in current.items():
            entry = _SESSIONS_CACHE.get(path)
            if entry is None or entry['mtime'] != mtime or entry['size'] != size:
                to_parse.append((path, f, mtime, size))

    # Parse the stale/new files OUTSIDE the lock (the expensive part).
    parsed = {}
    for path, f, mtime, size in to_parse:
        try:
            stat_holder = type('S', (), {'st_size': size, 'st_mtime': mtime})()
            meta = _parse_session_file(f, stat_holder)
            parsed[path] = {'mtime': mtime, 'size': size, 'meta': meta}
        except Exception:
            continue

    changed = False
    with _SESSIONS_CACHE_LOCK:
        # Apply freshly parsed entries.
        for path, entry in parsed.items():
            _SESSIONS_CACHE[path] = entry
            changed = True
        # Evict entries for files that no longer exist.
        for path in list(_SESSIONS_CACHE.keys()):
            if path not in current:
                del _SESSIONS_CACHE[path]
                changed = True
        # Build the result from the cache (only for currently-present files).
        for path in current:
            entry = _SESSIONS_CACHE.get(path)
            if entry:
                sessions.append(dict(entry['meta']))
        snapshot = dict(_SESSIONS_CACHE) if changed else None

    if snapshot is not None:
        _write_sessions_cache_to_disk(snapshot)

    sessions.sort(key=lambda s: s['mtime'], reverse=True)
    return sessions


def parse_conversation(session_id):
    """Parse a JSONL conversation file into structured messages for rendering."""
    f = CONVERSATIONS_DIR / f'{session_id}.jsonl'
    if not f.exists():
        return None

    messages = []
    with open(f) as fh:
        for line in fh:
            try:
                obj = json.loads(line)
                t = obj.get('type')

                if t == 'user':
                    msg = obj.get('message', {})
                    content = msg.get('content', '')
                    timestamp = obj.get('timestamp', '')
                    is_meta = obj.get('isMeta', False)
                    source_tool_id = obj.get('sourceToolUseID', '')

                    # Content can be a string (user text) or list (tool results)
                    blocks = []
                    if isinstance(content, str):
                        blocks.append({'type': 'text', 'text': content})
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict):
                                blocks.append(c)

                    messages.append({
                        'role': 'user',
                        'timestamp': timestamp,
                        'blocks': blocks,
                        'is_meta': is_meta,
                        'source_tool_id': source_tool_id,
                    })

                elif t == 'assistant':
                    msg = obj.get('message', {})
                    content = msg.get('content', [])
                    timestamp = obj.get('timestamp', '')

                    blocks = []
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict):
                                blocks.append(c)
                    elif isinstance(content, str):
                        blocks.append({'type': 'text', 'text': content})

                    messages.append({
                        'role': 'assistant',
                        'timestamp': timestamp,
                        'blocks': blocks,
                    })

            except (json.JSONDecodeError, KeyError):
                continue

    return messages


def _render_conversation_block(block, block_idx):
    """Render a single content block (text, thinking, tool_use, tool_result) as HTML."""
    btype = block.get('type', '')

    if btype == 'text':
        text = block.get('text', '')
        escaped = html_mod.escape(text)
        return f'<div class="conv-text"><div class="conv-markdown" data-raw="{html_mod.escape(text, quote=True)}">{escaped}</div></div>'

    elif btype == 'thinking':
        thinking = block.get('thinking', '')
        escaped = html_mod.escape(thinking)
        return f'''<details class="conv-thinking">
            <summary><span class="thinking-icon">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"><circle cx="7" cy="7" r="5.5"/><path d="M5.5 5.5c0-1.1.7-1.8 1.5-1.8s1.5.7 1.5 1.8c0 .8-.6 1.2-1.5 1.5v.8"/><circle cx="7" cy="9.5" r=".4" fill="currentColor"/></svg>
            </span>Thinking</summary>
            <div class="thinking-body"><pre>{escaped}</pre></div>
        </details>'''

    elif btype == 'tool_use':
        name = block.get('name', 'Unknown tool')
        inp = block.get('input', {})
        tool_id = block.get('id', '')

        # Build a human-readable summary line
        summary = _tool_use_summary(name, inp)

        # Build the detail body
        detail_html = _render_tool_input(name, inp)

        return f'''<details class="conv-tool-use" data-tool-id="{html_mod.escape(tool_id)}">
            <summary><span class="tool-icon">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 2.5l3 3-7.5 7.5H1v-3z"/><path d="M7 4l3 3"/></svg>
            </span><span class="tool-name">{html_mod.escape(name)}</span> <span class="tool-summary">{html_mod.escape(summary)}</span></summary>
            <div class="tool-body">{detail_html}</div>
        </details>'''

    elif btype == 'tool_result':
        tool_use_id = block.get('tool_use_id', '')
        content = block.get('content', '')
        is_error = block.get('is_error', False)

        result_text = ''
        if isinstance(content, str):
            result_text = content
        elif isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'text':
                    parts.append(c.get('text', ''))
            result_text = '\n'.join(parts)

        if len(result_text) > 5000:
            result_text = result_text[:5000] + f'\n\n... ({len(result_text) - 5000} more characters truncated)'

        escaped = html_mod.escape(result_text)
        error_class = ' tool-error' if is_error else ''

        return f'''<details class="conv-tool-result{error_class}" data-tool-id="{html_mod.escape(tool_use_id)}">
            <summary><span class="result-icon">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"><path d="M2.5 7.5l3 3 6-7"/></svg>
            </span>Result{' (error)' if is_error else ''} <span class="result-preview">{html_mod.escape(result_text[:80].replace(chr(10), " "))}</span></summary>
            <div class="result-body"><pre>{escaped}</pre></div>
        </details>'''

    return ''


def _tool_use_summary(name, inp):
    """Return a short human-readable summary of a tool call."""
    if name == 'Read':
        return inp.get('file_path', '')
    elif name == 'Write':
        return inp.get('file_path', '')
    elif name == 'Edit':
        fp = inp.get('file_path', '')
        return fp
    elif name == 'Bash':
        desc = inp.get('description', '')
        cmd = inp.get('command', '')
        return desc if desc else (cmd[:80] if cmd else '')
    elif name == 'Grep':
        pattern = inp.get('pattern', '')
        path = inp.get('path', '')
        return f'/{pattern}/ in {path}' if path else f'/{pattern}/'
    elif name == 'Glob':
        return inp.get('pattern', '')
    elif name == 'Agent':
        return inp.get('description', inp.get('prompt', '')[:80])
    elif name == 'Skill':
        return inp.get('skill', '')
    elif name == 'TodoWrite':
        return ''
    else:
        return ''


def _render_tool_input(name, inp):
    """Render tool input as formatted HTML, with special treatment for Edit diffs."""
    if name == 'Edit':
        fp = html_mod.escape(inp.get('file_path', ''))
        old_s = inp.get('old_string', '')
        new_s = inp.get('new_string', '')
        replace_all = inp.get('replace_all', False)

        # Render as a diff
        old_lines = old_s.splitlines(keepends=True)
        new_lines = new_s.splitlines(keepends=True)

        diff = difflib.unified_diff(old_lines, new_lines, lineterm='')
        diff_lines = list(diff)

        if diff_lines:
            diff_html = []
            for line in diff_lines:
                escaped_line = html_mod.escape(line.rstrip('\n'))
                if line.startswith('+') and not line.startswith('+++'):
                    diff_html.append(f'<span class="diff-add">{escaped_line}</span>')
                elif line.startswith('-') and not line.startswith('---'):
                    diff_html.append(f'<span class="diff-del">{escaped_line}</span>')
                elif line.startswith('@@'):
                    diff_html.append(f'<span class="diff-hunk">{escaped_line}</span>')
                else:
                    diff_html.append(f'<span class="diff-ctx">{escaped_line}</span>')
            replace_note = ' <span class="diff-flag">(replace all)</span>' if replace_all else ''
            return f'''<div class="tool-file">{fp}{replace_note}</div>
                <div class="diff-block"><pre>{"<br>".join(diff_html)}</pre></div>'''
        else:
            return f'<div class="tool-file">{fp}</div><div class="tool-note">No visible changes</div>'

    elif name == 'Write':
        fp = html_mod.escape(inp.get('file_path', ''))
        content = inp.get('content', '')
        if len(content) > 3000:
            content = content[:3000] + f'\n... ({len(content) - 3000} more characters)'
        escaped = html_mod.escape(content)
        return f'''<div class="tool-file">{fp}</div>
            <div class="code-block"><pre>{escaped}</pre></div>'''

    elif name == 'Bash':
        cmd = html_mod.escape(inp.get('command', ''))
        desc = html_mod.escape(inp.get('description', ''))
        desc_html = f'<div class="tool-desc">{desc}</div>' if desc else ''
        return f'''{desc_html}<div class="code-block"><pre><code class="language-bash">{cmd}</code></pre></div>'''

    elif name == 'Read':
        fp = html_mod.escape(inp.get('file_path', ''))
        offset = inp.get('offset', '')
        limit = inp.get('limit', '')
        range_str = ''
        if offset or limit:
            range_str = f' (lines {offset or 0}–{(offset or 0) + (limit or "?")})'
        return f'<div class="tool-file">{fp}{range_str}</div>'

    elif name == 'Grep':
        pattern = html_mod.escape(inp.get('pattern', ''))
        path = html_mod.escape(inp.get('path', '.'))
        glob_p = html_mod.escape(inp.get('glob', ''))
        return f'<div class="tool-file">Pattern: <code>{pattern}</code> in {path}{" glob: " + glob_p if glob_p else ""}</div>'

    elif name == 'Glob':
        pattern = html_mod.escape(inp.get('pattern', ''))
        path = html_mod.escape(inp.get('path', '.'))
        return f'<div class="tool-file">Pattern: <code>{pattern}</code> in {path}</div>'

    elif name == 'Agent':
        desc = html_mod.escape(inp.get('description', ''))
        prompt = inp.get('prompt', '')
        if len(prompt) > 1000:
            prompt = prompt[:1000] + '...'
        escaped_prompt = html_mod.escape(prompt)
        return f'''<div class="tool-desc">{desc}</div>
            <div class="code-block"><pre>{escaped_prompt}</pre></div>'''

    else:
        # Generic: show as JSON
        try:
            formatted = json.dumps(inp, indent=2)
            if len(formatted) > 3000:
                formatted = formatted[:3000] + '\n...'
            return f'<div class="code-block"><pre>{html_mod.escape(formatted)}</pre></div>'
        except Exception:
            return f'<div class="code-block"><pre>{html_mod.escape(str(inp))}</pre></div>'


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route('/')
def index():
    return redirect(f'/browse{BASE_DIR}')


# --- Cmd+K search palette: cached file/dir index ---
_SEARCH_EXTRA_SKIP = {'Library', '.Trash', 'venv', '.venv', 'site-packages',
                      'node_modules', '.git', '__pycache__'}
_SEARCH_HARD_SKIP = {'node_modules', '.git'}
_SEARCH_INDEX = {'entries': [], 'built_at': 0.0}
_SEARCH_INDEX_LOCK = threading.Lock()
_SEARCH_INDEX_TTL = 60.0
_SEARCH_MAX_CANDIDATES = 20000


def _build_search_index():
    """Walk BASE_DIR once, collecting up to _SEARCH_MAX_CANDIDATES (name, path, is_dir, mtime).

    Built with supervisor visibility (ring-agnostic); per-request results are
    filtered through is_path_allowed() so restricted paths never leak to
    lower-privilege visitors.
    """
    entries = []
    base = str(BASE_DIR)
    for root, dirs, files in os.walk(base):
        # Prune directories in-place so os.walk doesn't descend into them.
        pruned = []
        for d in dirs:
            if d in _SEARCH_HARD_SKIP:
                continue
            if d in SKIP_DIRS or d in _SEARCH_EXTRA_SKIP:
                continue
            if d.startswith('.') and d != '.claude':
                continue
            pruned.append(d)
        dirs[:] = pruned
        for d in dirs:
            full = os.path.join(root, d)
            try:
                mt = os.lstat(full).st_mtime
            except OSError:
                mt = 0.0
            entries.append((d, full, True, mt))
        for f in files:
            if f.startswith('.'):
                continue
            full = os.path.join(root, f)
            try:
                mt = os.lstat(full).st_mtime
            except OSError:
                mt = 0.0
            entries.append((f, full, False, mt))
        if len(entries) >= _SEARCH_MAX_CANDIDATES:
            break
    return entries


def _get_search_index():
    now = time.time()
    with _SEARCH_INDEX_LOCK:
        if now - _SEARCH_INDEX['built_at'] > _SEARCH_INDEX_TTL or not _SEARCH_INDEX['entries']:
            _SEARCH_INDEX['entries'] = _build_search_index()
            _SEARCH_INDEX['built_at'] = now
        return _SEARCH_INDEX['entries']


def _fuzzy_rank(name, q):
    """Return a rank score (lower is better) or None if q is not a subsequence of name.
    0 = prefix, 1 = word-boundary, 2 = substring, 3 = subsequence."""
    n = name.lower()
    if n.startswith(q):
        return 0
    idx = n.find(q)
    if idx != -1:
        prev = n[idx - 1] if idx > 0 else ''
        if idx == 0 or prev in ('-', '_', ' ', '.'):
            return 1
        return 2
    # subsequence check
    it = iter(n)
    if all(ch in it for ch in q):
        return 3
    return None


@app.route('/api/search')
def api_search():
    q = (request.args.get('q') or '').strip().lower()
    if not q:
        return jsonify([])
    ring = get_visitor()["ring"]
    entries = _get_search_index()
    scored = []
    for name, path, is_dir, mtime in entries:
        # Ring enforcement: drop any path the visitor isn't allowed to see.
        if not is_path_allowed(path, ring):
            continue
        rank = _fuzzy_rank(name, q)
        if rank is not None:
            scored.append((rank, -mtime, name, path, is_dir, mtime))
    scored.sort(key=lambda t: (t[0], t[1]))
    results = [{'name': name, 'path': path, 'is_dir': is_dir, 'mtime': mtime}
               for _r, _m, name, path, is_dir, mtime in scored[:40]]
    return jsonify(results)


@app.route('/save', methods=['POST'])
def save_file():
    try:
        visitor = get_visitor()
        data = request.get_json()
        file_path = Path(data['path']).resolve()

        if file_path.suffix.lower() != '.md':
            return jsonify(ok=False, error='Only .md files are editable'), 403
        if not file_path.is_relative_to(BASE_DIR):
            return jsonify(ok=False, error='File is outside the served directory'), 403
        if not is_path_allowed(str(file_path), visitor["ring"]):
            return jsonify(ok=False, error='Access denied'), 403

        # Conflict detection: if the caller tells us the mtime it started from,
        # refuse to clobber a file that changed on disk since (e.g. an agent edit).
        expected_mtime = data.get('expected_mtime')
        if expected_mtime is not None and file_path.exists():
            actual_mtime = file_path.stat().st_mtime
            if abs(actual_mtime - float(expected_mtime)) > 0.001:
                return jsonify(ok=False, conflict=True,
                               error='File changed on disk since you started editing',
                               current_mtime=actual_mtime), 409

        file_path.write_text(data['content'])
        return jsonify(ok=True, mtime=file_path.stat().st_mtime)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.route('/tasks')
def serve_tasks():
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return Response('Access denied — supervisors only', status=403)
    # original logic below
    jobs = get_launchd_jobs()

    # Generate timeline SVG
    timeline_html = generate_timeline_svg(jobs)

    cards = []
    for job in jobs:
        name = _strip_label_prefixes(job['label']).replace('-', ' ').title()

        if job['keep_alive'] or job['is_running']:
            dot_class = 'amber'
            sched_class = 'running'
            sched_label = 'Always running'
            card_status = 'status-running'
        elif job['is_loaded']:
            dot_class = 'green'
            sched_class = 'scheduled'
            sched_label = job['schedule']
            card_status = 'status-loaded'
        else:
            dot_class = 'gray'
            sched_class = 'scheduled'
            sched_label = job['schedule']
            card_status = ''

        last_run_str = ''
        if job['last_run']:
            last_run_str = f'{_time_ago(job["last_run"])}'

        cards.append(f'''<a href="/tasks/{job['label']}" style="text-decoration:none; color:inherit;">
            <div class="task-card {card_status}">
                <div class="task-name"><span class="status-dot {dot_class}"></span>{name}</div>
                <div class="task-desc">{job['description']}</div>
                <div class="task-meta">
                    <span class="task-schedule {sched_class}">{sched_label}</span>
                    <span class="task-last-run">{last_run_str}</span>
                </div>
            </div>
        </a>''')

    content = f'''<div class="tasks-page">
        <h1>Scheduled Tasks</h1>
        <div class="subtitle">{DISPLAY_NAME}'s daily rhythm</div>
        {timeline_html}
        <div class="task-grid">{"".join(cards)}</div>
    </div>'''

    return _render_page('Scheduled Tasks', content)


@app.route('/tasks/<path:label>')
def serve_task_detail(label):
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return Response('Access denied — supervisors only', status=403)
    jobs = get_launchd_jobs()
    job = None
    for j in jobs:
        if j['label'] == label:
            job = j
            break

    if not job:
        return Response(f'Task not found: {label}', status=404)

    name = _strip_label_prefixes(label).replace('-', ' ').title()

    # Extract claude -p prompt if this is a claude task
    prompt = extract_claude_prompt(job['script']) if job['script'] else None

    # Get run history WITH output extraction
    runs = get_run_history(prompt, with_output=True)

    # --- Status bar components ---
    is_running = job['is_running'] or job['keep_alive']
    if is_running:
        status_chip = '<span class="status-chip"><span class="status-dot amber"></span>Running</span>'
    elif job['is_loaded']:
        status_chip = '<span class="status-chip"><span class="status-dot green"></span>Loaded</span>'
    else:
        status_chip = '<span class="status-chip"><span class="status-dot gray"></span>Not loaded</span>'

    sched_class = 'always' if ('Always' in job['schedule'] or is_running) else ''
    schedule_chip = f'<span class="schedule-chip {sched_class}">{job["schedule"]}</span>'

    # Next run countdown
    next_run_html = ''
    next_info = get_next_run_time(job['schedule'])
    if next_info:
        _, human = next_info
        next_run_html = f'''<span class="divider"></span>
            <span class="next-run">Next in <span class="countdown">{human}</span></span>'''

    # Reliability strip
    strip_html = ''
    if prompt:
        strip = get_reliability_strip(prompt)
        today = datetime.now().date()
        dots = []
        for d, ran in strip:
            classes = 'strip-dot'
            classes += ' ran' if ran else ' missed'
            if d == today:
                classes += ' today'
            day_label = d.strftime('%b %-d')
            dots.append(f'<span class="{classes}" title="{day_label}"></span>')
        strip_html = f'''<span class="divider"></span>
            <span class="reliability-strip">
                <span class="strip-label">14d</span>
                {"".join(dots)}
            </span>'''

    status_bar = f'''<div class="task-status-bar">
        {status_chip}
        {schedule_chip}
        {next_run_html}
        {strip_html}
    </div>'''

    # --- Latest output hero ---
    latest_html = ''
    if runs and runs[0].get('output'):
        latest = runs[0]
        ago = _time_ago(latest['time'])
        time_str = latest['time'].strftime('%b %d at %H:%M')
        output_escaped = html_mod.escape(latest['output'])
        output_formatted = output_escaped.replace('\n\n', '</p><p>').replace('\n', '<br>')
        output_formatted = f'<p>{output_formatted}</p>'
        output_formatted = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', output_formatted)

        latest_html = f'''<div class="latest-output">
            <div class="section-label"><span class="pulse-dot"></span> Latest Output</div>
            <div class="output-card">
                <div class="output-meta">
                    <span class="timestamp">{time_str}</span>
                    <span>{ago}</span>
                </div>
                <div class="output-text" id="latest-text">{output_formatted}</div>
                <button class="expand-btn" onclick="
                    var el = document.getElementById('latest-text');
                    el.classList.toggle('expanded');
                    this.textContent = el.classList.contains('expanded') ? '\\u2191 Collapse' : '\\u2193 Show more';
                ">&#8595; Show more</button>
            </div>
        </div>'''
    elif not runs:
        latest_html = f'''<div class="latest-output">
            <div class="section-label">Latest Output</div>
            <div class="output-card">
                <div class="no-output">No recorded runs yet. This task hasn't been matched to any Claude Code sessions.</div>
            </div>
        </div>'''

    # --- Output feed (past runs) ---
    feed_html = ''
    feed_runs = runs[1:7] if len(runs) > 1 else []
    if feed_runs:
        items = []
        for i, run in enumerate(feed_runs):
            ago = _time_ago(run['time'])
            time_str = run['time'].strftime('%b %d, %H:%M')
            summary = ''
            full_output = ''
            if run.get('output'):
                raw = run['output']
                summary_text = raw[:200].replace('\n', ' ').strip()
                if len(raw) > 200:
                    summary_text += '...'
                summary = html_mod.escape(summary_text)
                full_escaped = html_mod.escape(raw)
                full_formatted = full_escaped.replace('\n\n', '</p><p>').replace('\n', '<br>')
                full_formatted = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', full_formatted)
                full_output = f'<div class="feed-full"><p>{full_formatted}</p></div>'
            else:
                summary = '<em style="color:var(--text-tertiary)">Session found, output not extracted</em>'

            items.append(f'''<div class="feed-item" onclick="this.classList.toggle('expanded')">
                <div class="feed-meta">
                    <span>{time_str}</span>
                    <span class="feed-ago">{ago}</span>
                </div>
                <div class="feed-summary">{summary}</div>
                {full_output}
            </div>''')

        feed_html = f'''<div class="output-feed">
            <div class="section-label">Recent Runs <span style="font-weight:normal; opacity:0.6;">({len(runs)} in last 14 days)</span></div>
            <div class="feed-timeline">{"".join(items)}</div>
        </div>'''

    # --- Collapsible config section ---
    script_link = f'<a href="/browse{job["script"]}">{job["script"]}</a>' if job['script'] else '&mdash;'
    plist_link = f'<a href="/browse{job["plist_path"]}">{Path(job["plist_path"]).name}</a>'
    last_run_text = job['last_run'].strftime('%b %d, %Y at %H:%M') if job['last_run'] else 'Never'

    prompt_html = ''
    if prompt:
        escaped_prompt = html_mod.escape(prompt)
        highlighted_prompt = re.sub(
            r'\$\{?\w+\}?',
            lambda m: f'<span class="bash-var">{m.group()}</span>',
            escaped_prompt
        )
        prompt_html = f'''<div class="prompt-section">
            <h3>Prompt</h3>
            <div class="prompt-box">{highlighted_prompt}</div>
        </div>'''

    # Logs
    stdout_content = ''
    stderr_content = ''
    if job['stdout_log'] and Path(job['stdout_log']).exists():
        try:
            lines = Path(job['stdout_log']).read_text(errors='replace').strip().splitlines()
            stdout_content = html_mod.escape('\n'.join(lines[-100:])) if lines else '<span class="log-empty">Empty</span>'
        except Exception:
            stdout_content = '<span class="log-empty">Could not read</span>'
    else:
        stdout_content = '<span class="log-empty">No log file</span>'

    if job['stderr_log'] and Path(job['stderr_log']).exists():
        try:
            lines = Path(job['stderr_log']).read_text(errors='replace').strip().splitlines()
            stderr_content = html_mod.escape('\n'.join(lines[-100:])) if lines else '<span class="log-empty">Empty</span>'
        except Exception:
            stderr_content = '<span class="log-empty">Could not read</span>'
    else:
        stderr_content = '<span class="log-empty">No log file</span>'

    config_html = f'''<div class="config-section">
        <button class="config-toggle" onclick="
            this.classList.toggle('open');
            this.nextElementSibling.classList.toggle('open');
        "><span class="chevron">&#9654;</span> Configuration &amp; Logs</button>
        <div class="config-body">
            <div class="detail-grid">
                <div class="detail-item">
                    <div class="label">Label</div>
                    <div class="value">{label}</div>
                </div>
                <div class="detail-item">
                    <div class="label">Last Activity</div>
                    <div class="value">{last_run_text}</div>
                </div>
                <div class="detail-item">
                    <div class="label">Script</div>
                    <div class="value">{script_link}</div>
                </div>
                <div class="detail-item">
                    <div class="label">Plist</div>
                    <div class="value">{plist_link}</div>
                </div>
            </div>
            {prompt_html}
            <div class="log-section">
                <h3>stdout</h3>
                <div class="log-box">{stdout_content}</div>
            </div>
            <div class="log-section">
                <h3>stderr</h3>
                <div class="log-box">{stderr_content}</div>
            </div>
        </div>
    </div>'''

    content = f'''<div class="task-detail">
        <a href="/tasks" class="task-detail-back">&larr; Back to all tasks</a>
        <div class="task-detail-header">
            <h1>{name}</h1>
            <div class="task-desc">{job['description']}</div>
        </div>
        {status_bar}
        {latest_html}
        {feed_html}
        {config_html}
    </div>'''

    return _render_page(f'Task: {name}', content)


# ============================================================
# CONVERSATIONS ROUTES
# ============================================================

@app.route('/conversations')
def serve_conversations():
    """Conversation index page — all sessions grouped by date."""
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return Response('Access denied — supervisors only', status=403)
    sessions = list_conversation_sessions()

    total = len(sessions)

    # Group by date label
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())

    groups = OrderedDict()
    for s in sessions:
        d = datetime.fromtimestamp(s['mtime']).date()
        if d == today:
            label = 'Today'
        elif d == yesterday:
            label = 'Yesterday'
        elif d >= week_start:
            label = 'This Week'
        else:
            label = d.strftime('%B %Y')

        if label not in groups:
            groups[label] = []
        groups[label].append(s)

    # Build rows — clean single-line per conversation
    marker_svg = '<svg class="conv-marker" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v12M2 8h12M4.5 4.5l7 7M11.5 4.5l-7 7"/></svg>'

    # Build tab headers and group sections
    tab_labels = list(groups.keys())
    tabs_html = []
    sections_html = []
    for idx, (label, items) in enumerate(groups.items()):
        tab_id = f'grp-{idx}'
        tabs_html.append(f'<a class="group-tab" href="#{tab_id}">{html_mod.escape(label)}</a>')

        rows = []
        for s in items:
            dt = datetime.fromtimestamp(s['mtime'])
            if label in ('Today', 'Yesterday'):
                time_str = dt.strftime('%-H:%M')
            else:
                time_str = dt.strftime('%-d %b')
            preview = s['preview'] or '<span style="color:var(--text-tertiary);font-style:italic">Scheduled task</span>'
            size_str = human_size(s['size'])
            kind = s.get('kind', 'terminal')
            source = s.get('source', 'Terminal')
            badge = f'<span class="conv-badge kind-{kind}">{html_mod.escape(source)}</span>'

            rows.append(f'''<div class="conv-row" data-kind="{kind}" onclick="window.location='/conversations/{s['id']}'">
                {marker_svg}
                <span class="conv-time">{time_str}</span>
                {badge}
                <span class="conv-info"><span class="conv-preview">{preview}</span></span>
                <span class="conv-size">{size_str}</span>
            </div>''')

        sections_html.append(f'''<div class="conv-group-section" id="{tab_id}">
            <div class="conv-section-label">{html_mod.escape(label)}</div>
            {"".join(rows)}
        </div>''')

    # Scroll-based tab highlighting JS
    tab_js = '''<script>
    (function() {
        var tabs = document.querySelectorAll('.group-tab');
        var sections = document.querySelectorAll('.conv-group-section');
        function updateActive() {
            var scrollTop = window.scrollY || document.documentElement.scrollTop;
            var current = 0;
            sections.forEach(function(s, i) {
                if (s.getBoundingClientRect().top <= 120) current = i;
            });
            tabs.forEach(function(t) { t.classList.remove('active'); });
            if (tabs[current]) tabs[current].classList.add('active');
        }
        window.addEventListener('scroll', updateActive);
        updateActive();
    })();
    </script>'''

    filter_bar = '''<div class="conv-filter-bar">
        <span class="conv-filter-chip" data-filter="all">All</span>
        <span class="conv-filter-chip" data-filter="conversations">Conversations</span>
        <span class="conv-filter-chip" data-filter="scheduled">Scheduled</span>
    </div>'''

    filter_js = '''<script>
    (function() {
        var index = document.getElementById('convIndex');
        var chips = document.querySelectorAll('.conv-filter-chip');
        var sections = document.querySelectorAll('.conv-group-section');
        function apply(mode) {
            index.classList.remove('filter-conversations', 'filter-scheduled');
            if (mode === 'conversations') index.classList.add('filter-conversations');
            else if (mode === 'scheduled') index.classList.add('filter-scheduled');
            chips.forEach(function(c) { c.classList.toggle('active', c.dataset.filter === mode); });
            sections.forEach(function(s) {
                var visible = 0;
                s.querySelectorAll('.conv-row').forEach(function(r) {
                    if (r.offsetParent !== null) visible++;
                });
                s.style.display = visible === 0 ? 'none' : '';
            });
        }
        var saved = localStorage.getItem('convFilter') || 'all';
        chips.forEach(function(c) {
            c.addEventListener('click', function() {
                localStorage.setItem('convFilter', c.dataset.filter);
                apply(c.dataset.filter);
            });
        });
        apply(saved);
    })();
    </script>'''

    content = f'''<div class="conv-index" id="convIndex">
        <div class="conv-index-header">
            <h1>Conversations</h1>
            <div class="subtitle">{total} sessions</div>
        </div>
        {filter_bar}
        <div class="conv-group-tabs">{"".join(tabs_html)}</div>
        {"".join(sections_html)}
    </div>
    {tab_js}
    {filter_js}'''

    return _render_page('Conversations', content)


def _render_message_html(msg):
    """Render a single conversation message dict to HTML. Shared by the
    page route and the infinite-scroll API. Keeps skill/meta collapsing."""
    role = msg['role']
    timestamp = msg.get('timestamp', '')
    is_meta = msg.get('is_meta', False)
    source_tool_id = msg.get('source_tool_id', '')
    ts_display = ''
    if timestamp:
        try:
            ts_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            ts_display = ts_dt.strftime('%-H:%M:%S')
        except Exception:
            pass

    role_label = 'You' if role == 'user' else DISPLAY_NAME

    # Detect skill/meta messages: collapse them
    if role == 'user' and is_meta and source_tool_id:
        # Extract skill name from content if possible
        skill_name = ''
        for block in msg['blocks']:
            text = block.get('text', '')
            if isinstance(text, str) and 'Base directory for this skill' in text:
                # Try to extract skill path
                match = re.search(r'skills/([^/\n]+)', text)
                if match:
                    skill_name = match.group(1)
                break
        label = f'Skill loaded: {skill_name}' if skill_name else 'Skill prompt loaded'
        # Count approximate size
        total_chars = sum(len(b.get('text', '')) for b in msg['blocks'])
        size_note = f'{total_chars:,} chars'

        return f'''<div class="conv-message role-{role} conv-meta-msg">
                <details class="conv-skill-loaded">
                    <summary>
                        <span class="skill-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 1.5v11"/><path d="M3.5 5l3.5-3.5L10.5 5"/><path d="M2 8.5h10"/><path d="M4 11h6"/></svg></span>
                        {html_mod.escape(label)} <span class="skill-size">({size_note})</span>
                    </summary>
                    <div class="skill-body">{''.join(_render_conversation_block(b, i) for i, b in enumerate(msg['blocks']))}</div>
                </details>
            </div>'''

    blocks_html = []
    for i, block in enumerate(msg['blocks']):
        blocks_html.append(_render_conversation_block(block, i))

    return f'''<div class="conv-message role-{role}">
            <div class="conv-role-label">{role_label} <span class="conv-ts">{ts_display}</span></div>
            {"".join(blocks_html)}
        </div>'''


@app.route('/api/conversations/<session_id>/messages')
def api_conversation_messages(session_id):
    """Return a rendered chunk of conversation messages for infinite scroll."""
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return jsonify(error='Access denied — supervisors only'), 403
    messages = parse_conversation(session_id)
    if messages is None:
        return jsonify(error=f'Conversation not found: {session_id}'), 404

    total = len(messages)
    try:
        offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.args.get('limit', 100))
    except (TypeError, ValueError):
        limit = 100
    offset = max(0, offset)
    limit = max(1, min(limit, 300))

    chunk = messages[offset:offset + limit]
    html = ''.join(_render_message_html(m) for m in chunk)
    return jsonify(html=html, offset=offset, count=len(chunk), total=total)


@app.route('/api/conversations/<session_id>/live')
def api_conversation_live(session_id):
    """Return messages after index N for a (possibly live) conversation session."""
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return jsonify({'error': 'Access denied — supervisors only'}), 403
    messages = parse_conversation(session_id)
    if messages is None:
        return jsonify({'error': 'not found'}), 404

    f = CONVERSATIONS_DIR / f'{session_id}.jsonl'
    try:
        mtime = f.stat().st_mtime
    except OSError:
        return jsonify({'error': 'not found'}), 404
    live = (datetime.now() - datetime.fromtimestamp(mtime)).total_seconds() < 120

    try:
        after = int(request.args.get('after', 0))
    except (TypeError, ValueError):
        after = 0
    if after < 0:
        after = 0

    html = ''.join(_render_message_html(m) for m in messages[after:])
    return jsonify({'total': len(messages), 'live': live, 'html': html})


@app.route('/conversations/<session_id>')
def serve_conversation_detail(session_id):
    """Render a single conversation session."""
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return Response('Access denied — supervisors only', status=403)
    messages = parse_conversation(session_id)
    if messages is None:
        return Response(f'Conversation not found: {session_id}', status=404)

    # Get file metadata
    f = CONVERSATIONS_DIR / f'{session_id}.jsonl'
    stat = f.stat()
    dt = datetime.fromtimestamp(stat.st_mtime)
    is_live = (datetime.now() - dt).total_seconds() < 120

    # Calculate duration
    duration_str = ''
    if messages:
        first_ts = None
        last_ts = None
        for m in messages:
            ts = m.get('timestamp', '')
            if ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts
        if first_ts and last_ts:
            try:
                t1 = datetime.fromisoformat(first_ts.replace('Z', '+00:00'))
                t2 = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
                diff_secs = int((t2 - t1).total_seconds())
                if diff_secs < 60:
                    duration_str = f'{diff_secs}s'
                elif diff_secs < 3600:
                    duration_str = f'{diff_secs // 60}m'
                else:
                    h = diff_secs // 3600
                    m_r = (diff_secs % 3600) // 60
                    duration_str = f'{h}h {m_r}m' if m_r else f'{h}h'
            except Exception:
                pass

    user_count = sum(1 for m in messages if m['role'] == 'user')
    assistant_count = sum(1 for m in messages if m['role'] == 'assistant')
    date_str = dt.strftime('%A, %B %-d, %Y at %-H:%M')

    # Render messages (limit initial render for very large conversations)
    max_initial = int(request.args.get('limit', 100))
    total_msgs = len(messages)
    render_msgs = messages[:max_initial]

    msgs_html = [_render_message_html(msg) for msg in render_msgs]

    # Infinite-scroll sentinel if truncated
    load_more = ''
    if total_msgs > max_initial:
        load_more = f'''<div id="conv-sentinel" data-session="{html_mod.escape(session_id, quote=True)}" data-offset="{max_initial}" data-total="{total_msgs}">
            <span class="conv-sentinel-label">loading older messages&hellip;</span>
        </div>'''

    # Live polling script (only when session is being actively written)
    live_poll_js = ''
    if is_live:
        live_poll_js = '''
    <script>
    (function() {
        var SESSION_ID = ''' + json.dumps(session_id) + ''';
        var count = ''' + str(len(render_msgs)) + ''';
        var deadPolls = 0;
        var timer = null;
        var container = document.querySelector('.conv-detail');
        var indicator = document.getElementById('conv-live-indicator');

        function renderMarkdown(scope) {
            scope.querySelectorAll('.conv-markdown[data-raw]').forEach(function(el) {
                if (typeof marked !== 'undefined') {
                    try {
                        el.innerHTML = marked.parse(el.getAttribute('data-raw'));
                        el.querySelectorAll('pre code').forEach(function(block) {
                            if (typeof hljs !== 'undefined') hljs.highlightElement(block);
                        });
                    } catch(e) {}
                }
            });
        }

        function stopPolling() {
            if (timer) { clearInterval(timer); timer = null; }
            if (indicator) {
                indicator.classList.add('ended');
                indicator.innerHTML = '<span class="conv-live-dot"></span>ended';
            }
        }

        function poll() {
            fetch('/api/conversations/' + SESSION_ID + '/live?after=' + count)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.html && data.total > count) {
                        var nearBottom = (window.innerHeight + window.scrollY) >= (document.body.scrollHeight - 200);
                        var tmp = document.createElement('div');
                        tmp.innerHTML = data.html;
                        var loadMore = container.querySelector('#conv-sentinel');
                        var newNodes = [];
                        while (tmp.firstChild) {
                            var node = tmp.firstChild;
                            tmp.removeChild(node);
                            if (loadMore) { container.insertBefore(node, loadMore); }
                            else { container.appendChild(node); }
                            if (node.nodeType === 1) newNodes.push(node);
                        }
                        newNodes.forEach(renderMarkdown);
                        count = data.total;
                        if (nearBottom) { window.scrollTo(0, document.body.scrollHeight); }
                    }
                    if (data.live) { deadPolls = 0; }
                    else { deadPolls++; if (deadPolls >= 3) { stopPolling(); } }
                })
                .catch(function() {});
        }

        timer = setInterval(poll, 5000);
    })();
    </script>'''

    content = f'''<div class="conv-detail">
        <div class="conv-detail-topbar">
            <a href="/conversations" class="conv-detail-back">&larr; All conversations</a>
        </div>
        <div class="conv-detail-header">
            <h1>{date_str}</h1>
            <div class="conv-header-meta">
                <span>{user_count + assistant_count} messages</span>
                {f'<span>{duration_str}</span>' if duration_str else ''}
                <span>{human_size(stat.st_size)}</span>
                <span style="opacity:0.5">{session_id[:8]}</span>
                {'<span class="conv-live-indicator" id="conv-live-indicator"><span class="conv-live-dot"></span>live</span>' if is_live else ''}
            </div>
        </div>
        {"".join(msgs_html)}
        {load_more}
    </div>
    <script>
    // Render markdown + highlight code within a given root (defaults to document)
    function convRenderMarkdown(root) {{
        (root || document).querySelectorAll('.conv-markdown[data-raw]').forEach(function(el) {{
            if (typeof marked !== 'undefined') {{
                try {{
                    var raw = el.getAttribute('data-raw');
                    el.innerHTML = marked.parse(raw);
                    el.querySelectorAll('pre code').forEach(function(block) {{
                        if (typeof hljs !== 'undefined') hljs.highlightElement(block);
                    }});
                }} catch(e) {{
                    // fallback to escaped text already in element
                }}
            }}
        }});
    }}
    convRenderMarkdown(document);

    // Infinite scroll: load older messages as the sentinel comes into view
    (function() {{
        var sentinel = document.getElementById('conv-sentinel');
        if (!sentinel || !('IntersectionObserver' in window)) return;
        var loading = false;

        function loadMore() {{
            if (loading) return;
            var offset = parseInt(sentinel.getAttribute('data-offset'), 10) || 0;
            var total = parseInt(sentinel.getAttribute('data-total'), 10) || 0;
            if (offset >= total) {{ observer.disconnect(); sentinel.remove(); return; }}
            loading = true;
            var session = sentinel.getAttribute('data-session');
            fetch('/api/conversations/' + encodeURIComponent(session) + '/messages?offset=' + offset + '&limit=100')
                .then(function(r) {{ return r.json(); }})
                .then(function(data) {{
                    var tmp = document.createElement('div');
                    tmp.innerHTML = data.html;
                    var nodes = Array.prototype.slice.call(tmp.children);
                    nodes.forEach(function(node) {{ sentinel.parentNode.insertBefore(node, sentinel); }});
                    nodes.forEach(function(node) {{ convRenderMarkdown(node); }});
                    var newOffset = data.offset + data.count;
                    sentinel.setAttribute('data-offset', newOffset);
                    sentinel.setAttribute('data-total', data.total);
                    loading = false;
                    if (newOffset >= data.total || data.count === 0) {{
                        observer.disconnect();
                        sentinel.remove();
                    }} else if (isVisible(sentinel)) {{
                        loadMore();
                    }}
                }})
                .catch(function() {{ loading = false; }});
        }}

        function isVisible(el) {{
            var r = el.getBoundingClientRect();
            return r.top < window.innerHeight && r.bottom > 0;
        }}

        var observer = new IntersectionObserver(function(entries) {{
            entries.forEach(function(entry) {{ if (entry.isIntersecting) loadMore(); }});
        }}, {{ rootMargin: '400px' }});
        observer.observe(sentinel);
    }})();
    </script>{live_poll_js}'''

    return _render_page(f'Conversation: {date_str}', content)


# ============================================================
# COMMENTS — Figma-style pins on served .html pages
# ------------------------------------------------------------
# A comment is stored in a `<file>.comments.json` sidecar next to the file it
# points at. The overlay below is injected at serve time into /raw/*.html —
# the file on disk is never modified. Your AI reads and resolves the comments
# with these same endpoints:
#
#   curl -s "http://HOST:PORT/comments?path=/abs/file.html"
#   curl -s -X POST "http://HOST:PORT/comments" -H "Content-Type: application/json" \
#        -d '{"path":"/abs/file.html","action":"resolve","id":"<id>"}'
# ============================================================


def _comments_file_for(path_str):
    """(sidecar Path, error string) for a requested file. Error is None when allowed."""
    p = Path(path_str).resolve()
    try:
        p.relative_to(BASE_DIR.resolve())
    except ValueError:
        return None, 'outside the browsable directory'
    if not is_path_allowed(str(p), get_visitor()["ring"]):
        return None, 'not allowed'
    return Path(str(p) + '.comments.json'), None


@app.route('/comments', methods=['GET'])
def get_comments():
    sidecar, err = _comments_file_for(request.args.get('path', ''))
    if err:
        return jsonify([]), 403
    if sidecar.exists():
        try:
            return jsonify(json.loads(sidecar.read_text()))
        except Exception:
            return jsonify([])
    return jsonify([])


@app.route('/comments', methods=['POST'])
def save_comment():
    try:
        data = request.get_json() or {}
        sidecar, err = _comments_file_for(data.get('path', ''))
        if err:
            return jsonify(ok=False, error=err), 403

        comments = json.loads(sidecar.read_text()) if sidecar.exists() else []
        action = data.get('action', 'add')

        if action == 'add':
            comment = {
                'id': str(uuid.uuid4())[:8],
                'anchor_text': data.get('anchor_text', ''),
                'comment': data['comment'],
                'timestamp': datetime.now().isoformat(),
                'resolved': False,
            }
            # Element comments carry the CSS selector of what they point at
            for extra in ('selector', 'snippet', 'tag'):
                if data.get(extra):
                    comment[extra] = data[extra]
            comments.append(comment)
        elif action in ('resolve', 'unresolve'):
            for c in comments:
                if c['id'] == data['id']:
                    c['resolved'] = (action == 'resolve')
                    break
        elif action == 'delete':
            comments = [c for c in comments if c['id'] != data['id']]

        if comments:
            sidecar.write_text(json.dumps(comments, indent=2))
        elif sidecar.exists():
            sidecar.unlink()  # an empty sidecar is just litter

        return jsonify(ok=True, comments=comments)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


ELEMENT_COMMENT_JS = r'''
<script>
(function () {
  if (window.__fxElementComments) return;
  window.__fxElementComments = true;

  var FILE_PATH = document.currentScript && document.currentScript.getAttribute('data-file-path');
  if (!FILE_PATH) {
    var m = document.querySelector('meta[name="fx-file-path"]');
    FILE_PATH = m ? m.getAttribute('content') : '';
  }
  if (!FILE_PATH) return;

  var comments = [];
  var mode = false;
  var hovered = null;
  var root, toggleBtn, highlight, pinLayer, popover, orphanPanel, detail;

  // ---------- styles ----------
  var css = [
    // The popovers/toggle/panel hang off <body>, not #fx-ec-root, so they must be named
    // here too or they inherit the host page's box model and the textarea overflows.
    '#fx-ec-root, #fx-ec-root *, #fx-ec-toggle, #fx-ec-toggle *, #fx-ec-pop, #fx-ec-pop *,',
    '#fx-ec-detail, #fx-ec-detail *, #fx-ec-orphans, #fx-ec-orphans *, #fx-ec-hl',
    '  { box-sizing: border-box; font-family: ui-monospace, "JetBrains Mono", SFMono-Regular, Menlo, monospace; }',
    '#fx-ec-root { position: fixed; z-index: 2147483000; top: 0; left: 0; width: 0; height: 0; }',
    '#fx-ec-toggle { position: fixed; right: 16px; bottom: 16px; z-index: 2147483001; display: inline-flex; align-items: center; gap: 7px;',
    '  padding: 8px 13px; border-radius: 999px; border: 1px solid #3D3835; background: #1C1917; color: #D4A574;',
    '  font-size: 12px; line-height: 1; cursor: pointer; box-shadow: 0 2px 10px rgba(0,0,0,.35); }',
    '#fx-ec-toggle:hover { background: #292524; }',
    '#fx-ec-toggle.on { background: #D4A574; color: #1C1917; border-color: #D4A574; }',
    '#fx-ec-toggle .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; display: inline-block; }',
    '#fx-ec-hl { position: fixed; z-index: 2147482900; pointer-events: none; border: 2px solid #D4A574; border-radius: 3px;',
    '  background: rgba(212,165,116,.10); display: none; }',
    '.fx-ec-pin { position: fixed; z-index: 2147482950; width: 24px; height: 24px; border-radius: 50% 50% 50% 2px;',
    '  background: #D4A574; color: #1C1917; font-size: 11px; font-weight: 700; display: flex; align-items: center;',
    '  justify-content: center; cursor: pointer; box-shadow: 0 1px 6px rgba(0,0,0,.4); border: 1px solid #8a6a44; }',
    '.fx-ec-pin:hover { background: #E0B88A; }',
    '#fx-ec-pop, #fx-ec-detail { position: fixed; z-index: 2147483002; width: 268px; max-width: calc(100vw - 16px);',
    '  max-height: calc(100vh - 16px); overflow: auto; background: #1C1917; color: #E7E5E4;',
    '  border: 1px solid #3D3835; border-radius: 8px; padding: 11px; box-shadow: 0 6px 24px rgba(0,0,0,.5); display: none; }',
    '#fx-ec-pop textarea { display: block; width: 100%; max-width: 100%; min-width: 0; height: 74px; margin: 0;',
    '  resize: vertical; background: #292524; color: #E7E5E4; line-height: 1.5;',
    '  border: 1px solid #3D3835; border-radius: 5px; padding: 7px; font-size: 12px; outline: none; }',
    '#fx-ec-pop textarea:focus { border-color: #D4A574; }',
    '.fx-ec-target { font-size: 10px; color: #A8A29E; margin-bottom: 7px; word-break: break-all; line-height: 1.4; }',
    '.fx-ec-row { display: flex; gap: 7px; justify-content: flex-end; margin-top: 8px; }',
    '.fx-ec-btn { padding: 5px 11px; border-radius: 5px; border: 1px solid #3D3835; background: #292524; color: #E7E5E4;',
    '  font-size: 11px; cursor: pointer; }',
    '.fx-ec-btn:hover { background: #332E2B; }',
    '.fx-ec-btn.primary { background: #D4A574; color: #1C1917; border-color: #D4A574; }',
    '.fx-ec-body { font-size: 12px; line-height: 1.55; white-space: pre-wrap; color: #E7E5E4; font-family: ui-serif, Literata, Georgia, serif; }',
    '.fx-ec-meta { font-size: 10px; color: #78716C; margin-top: 6px; }',
    '#fx-ec-orphans { position: fixed; left: 16px; bottom: 16px; z-index: 2147483001; width: 280px; background: #1C1917;',
    '  border: 1px solid #3D3835; border-radius: 8px; color: #E7E5E4; display: none; box-shadow: 0 4px 18px rgba(0,0,0,.45); }',
    '#fx-ec-orphans .hd { padding: 8px 11px; font-size: 11px; color: #D08770; cursor: pointer; display: flex; gap: 6px; align-items: center; }',
    '#fx-ec-orphans .bd { display: none; max-height: 42vh; overflow: auto; border-top: 1px solid #2D2926; padding: 4px 0; }',
    '#fx-ec-orphans.open .bd { display: block; }',
    '#fx-ec-orphans .it { padding: 9px 11px; border-bottom: 1px solid #2D2926; }',
    '#fx-ec-orphans .it:last-child { border-bottom: none; }',
    '#fx-ec-orphans .tag { display: inline-block; font-size: 9px; letter-spacing: .06em; text-transform: uppercase;',
    '  color: #D08770; border: 1px solid #D08770; border-radius: 3px; padding: 1px 5px; margin-bottom: 5px; }'
  ].join('\n');

  // ---------- selector ----------
  function esc(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/([^\w-])/g, '\\$1');
  }
  function cssPath(el) {
    if (el.id) return '#' + esc(el.id);
    var parts = [];
    var node = el;
    while (node && node.nodeType === 1 && node !== document.body && node !== document.documentElement) {
      if (node.id) { parts.unshift('#' + esc(node.id)); break; }
      var parent = node.parentNode;
      var idx = 1;
      if (parent && parent.children) {
        var n = 0;
        for (var i = 0; i < parent.children.length; i++) {
          var sib = parent.children[i];
          if (sib.tagName === node.tagName) { n++; if (sib === node) idx = n; }
        }
      }
      parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + idx + ')');
      node = parent;
    }
    if (!parts.length || parts[0].charAt(0) !== '#') parts.unshift('body');
    return parts.join(' > ');
  }

  // ---------- api ----------
  function post(payload) {
    payload.path = FILE_PATH;
    return fetch('/comments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (res && res.comments) comments = res.comments;
      render();
      return res;
    });
  }
  function load() {
    return fetch('/comments?path=' + encodeURIComponent(FILE_PATH))
      .then(function (r) { return r.json(); })
      .then(function (d) { comments = Array.isArray(d) ? d : []; render(); })
      .catch(function () { comments = []; render(); });
  }

  // ---------- render ----------
  function elementComments() {
    return comments.filter(function (c) { return c.selector && !c.resolved; });
  }
  function render() {
    pinLayer.innerHTML = '';
    var orphans = [];
    var n = 0;
    elementComments().forEach(function (c) {
      var el = null;
      try { el = document.querySelector(c.selector); } catch (e) { el = null; }
      if (!el) { orphans.push(c); return; }
      n++;
      var pin = document.createElement('div');
      pin.className = 'fx-ec-pin';
      pin.textContent = n;
      pin.setAttribute('data-id', c.id);
      pin.title = c.comment;
      pin._target = el;
      pin.addEventListener('click', function (ev) {
        ev.stopPropagation(); ev.preventDefault();
        showDetail(c, pin);
      });
      pinLayer.appendChild(pin);
    });
    positionPins();
    renderOrphans(orphans);
  }
  function positionPins() {
    var pins = pinLayer.children;
    for (var i = 0; i < pins.length; i++) {
      var pin = pins[i];
      var el = pin._target;
      if (!el || !el.isConnected) { pin.style.display = 'none'; continue; }
      var r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) { pin.style.display = 'none'; continue; }
      pin.style.display = 'flex';
      pin.style.left = Math.max(2, r.left - 11) + 'px';
      pin.style.top = Math.max(2, r.top - 11) + 'px';
    }
  }
  function renderOrphans(list) {
    if (!list.length) { orphanPanel.style.display = 'none'; return; }
    orphanPanel.style.display = 'block';
    var bd = orphanPanel.querySelector('.bd');
    bd.innerHTML = '';
    list.forEach(function (c) {
      var it = document.createElement('div');
      it.className = 'it';
      var tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = 'element deleted';
      var body = document.createElement('div');
      body.className = 'fx-ec-body';
      body.textContent = c.comment;
      var meta = document.createElement('div');
      meta.className = 'fx-ec-meta';
      meta.textContent = c.selector;
      var row = document.createElement('div');
      row.className = 'fx-ec-row';
      var btn = document.createElement('button');
      btn.className = 'fx-ec-btn';
      btn.textContent = 'Resolve';
      btn.addEventListener('click', function () { post({ action: 'resolve', id: c.id }); });
      row.appendChild(btn);
      it.appendChild(tag); it.appendChild(body); it.appendChild(meta); it.appendChild(row);
      bd.appendChild(it);
    });
    orphanPanel.querySelector('.hd-count').textContent = list.length;
  }

  // ---------- popovers ----------
  function place(box, x, y) {
    // Measure at the origin so a stale position can't shrink/wrap the box.
    box.style.left = '0px';
    box.style.top = '0px';
    box.style.display = 'block';
    var w = box.offsetWidth, h = box.offsetHeight;
    // Clamp low LAST: if the box is taller/wider than the room below/right of the
    // click, (innerHeight - h - 8) goes negative and must not win, or the popover
    // gets clipped by the top/left viewport edge.
    var left = Math.max(8, Math.min(x, window.innerWidth - w - 8));
    var top = Math.max(8, Math.min(y, window.innerHeight - h - 8));
    box.style.left = left + 'px';
    box.style.top = top + 'px';
  }
  function anyPopoverOpen() {
    return popover.style.display === 'block' || detail.style.display === 'block' ||
      orphanPanel.classList.contains('open');
  }
  function insidePopover(el) {
    return !!(el && el.closest && el.closest('#fx-ec-pop, #fx-ec-detail, #fx-ec-orphans'));
  }
  function hideAll() {
    popover.style.display = 'none'; detail.style.display = 'none';
    orphanPanel.classList.remove('open');
  }

  function openComposer(el, x, y) {
    var selector = cssPath(el);
    var snippet = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120);
    popover.innerHTML = '';
    var t = document.createElement('div');
    t.className = 'fx-ec-target';
    t.textContent = snippet ? snippet.slice(0, 60) : el.tagName.toLowerCase();
    var ta = document.createElement('textarea');
    ta.placeholder = 'Comment on this element...';
    var row = document.createElement('div');
    row.className = 'fx-ec-row';
    var cancel = document.createElement('button');
    cancel.className = 'fx-ec-btn'; cancel.textContent = 'Cancel';
    cancel.addEventListener('click', hideAll);
    var save = document.createElement('button');
    save.className = 'fx-ec-btn primary'; save.textContent = 'Save';
    function doSave() {
      var text = ta.value.trim();
      if (!text) { hideAll(); return; }
      hideAll();
      post({
        action: 'add',
        comment: text,
        selector: selector,
        snippet: snippet,
        tag: el.tagName.toLowerCase(),
        anchor_text: snippet
      });
      setMode(false);
    }
    save.addEventListener('click', doSave);
    ta.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) doSave();
      if (e.key === 'Escape') hideAll();
    });
    row.appendChild(cancel); row.appendChild(save);
    popover.appendChild(t); popover.appendChild(ta); popover.appendChild(row);
    place(popover, x + 12, y + 12);
    ta.focus();
  }

  function showDetail(c, pin) {
    detail.innerHTML = '';
    var body = document.createElement('div');
    body.className = 'fx-ec-body';
    body.textContent = c.comment;
    var meta = document.createElement('div');
    meta.className = 'fx-ec-meta';
    meta.textContent = (c.timestamp || '').slice(0, 16).replace('T', ' ');
    var row = document.createElement('div');
    row.className = 'fx-ec-row';
    var close = document.createElement('button');
    close.className = 'fx-ec-btn'; close.textContent = 'Close';
    close.addEventListener('click', hideAll);
    var res = document.createElement('button');
    res.className = 'fx-ec-btn primary'; res.textContent = 'Resolve';
    res.addEventListener('click', function () { hideAll(); post({ action: 'resolve', id: c.id }); });
    row.appendChild(close); row.appendChild(res);
    detail.appendChild(body); detail.appendChild(meta); detail.appendChild(row);
    var r = pin.getBoundingClientRect();
    place(detail, r.left + 28, r.top);
  }

  // ---------- comment mode ----------
  function isOurs(el) { return el && el.closest && !!el.closest('#fx-ec-root, #fx-ec-toggle, #fx-ec-pop, #fx-ec-detail, #fx-ec-orphans, #fx-ec-hl'); }

  function onMove(e) {
    if (!mode) return;
    // While a popover is open, hover-select is parked — no outlines chasing the cursor.
    if (anyPopoverOpen()) { highlight.style.display = 'none'; hovered = null; return; }
    var el = e.target;
    if (isOurs(el)) { highlight.style.display = 'none'; hovered = null; return; }
    hovered = el;
    var r = el.getBoundingClientRect();
    highlight.style.display = 'block';
    highlight.style.left = r.left + 'px';
    highlight.style.top = r.top + 'px';
    highlight.style.width = r.width + 'px';
    highlight.style.height = r.height + 'px';
  }
  // A click outside an open popover only dismisses it. It must not also open a new
  // composer, follow a link on the host page, or start a text selection.
  function onDown(e) {
    if (anyPopoverOpen() && !insidePopover(e.target) && !isOurs(e.target)) {
      e.preventDefault();
      e.stopPropagation();
    }
  }
  function onClick(e) {
    if (anyPopoverOpen() && !insidePopover(e.target)) {
      hideAll();
      // Our own controls (pin, toggle, orphan panel) still get their click.
      if (!isOurs(e.target)) { e.preventDefault(); e.stopPropagation(); }
      return;
    }
    if (!mode) return;
    if (isOurs(e.target)) return;
    e.preventDefault(); e.stopPropagation();
    openComposer(e.target, e.clientX, e.clientY);
  }
  function setMode(on) {
    mode = on;
    toggleBtn.classList.toggle('on', on);
    toggleBtn.querySelector('.lbl').textContent = on ? 'Click an element' : 'Comment';
    if (!on) { highlight.style.display = 'none'; }
  }

  // ---------- boot ----------
  function init() {
    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    root = document.createElement('div');
    root.id = 'fx-ec-root';
    document.body.appendChild(root);

    pinLayer = document.createElement('div');
    root.appendChild(pinLayer);

    highlight = document.createElement('div');
    highlight.id = 'fx-ec-hl';
    document.body.appendChild(highlight);

    toggleBtn = document.createElement('button');
    toggleBtn.id = 'fx-ec-toggle';
    toggleBtn.innerHTML = '<span class="dot"></span><span class="lbl">Comment</span>';
    toggleBtn.addEventListener('click', function (e) { e.stopPropagation(); hideAll(); setMode(!mode); });
    document.body.appendChild(toggleBtn);

    popover = document.createElement('div');
    popover.id = 'fx-ec-pop';
    document.body.appendChild(popover);

    detail = document.createElement('div');
    detail.id = 'fx-ec-detail';
    document.body.appendChild(detail);

    orphanPanel = document.createElement('div');
    orphanPanel.id = 'fx-ec-orphans';
    orphanPanel.innerHTML = '<div class="hd">&#9662; <span class="hd-count">0</span> comment(s) on deleted elements</div><div class="bd"></div>';
    orphanPanel.querySelector('.hd').addEventListener('click', function () { orphanPanel.classList.toggle('open'); });
    document.body.appendChild(orphanPanel);

    document.addEventListener('mousemove', onMove, true);
    document.addEventListener('mousedown', onDown, true);
    document.addEventListener('click', onClick, true);
    window.addEventListener('scroll', positionPins, true);
    window.addEventListener('resize', positionPins);
    setInterval(positionPins, 700);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { hideAll(); setMode(false); } });

    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
</script>
'''


def _inject_element_comments(html_text, abs_path):
    """Inject the element-comment overlay before </body>. Never touches disk."""
    tag = ('<meta name="fx-file-path" content="%s">\n' % html_mod.escape(str(abs_path), quote=True)
           + ELEMENT_COMMENT_JS)
    lower = html_text.lower()
    idx = lower.rfind('</body>')
    if idx != -1:
        return html_text[:idx] + tag + html_text[idx:]
    return html_text + tag





@app.route('/raw/<path:filepath>')
def serve_raw_file(filepath):
    """Serve a file with its native MIME type."""
    visitor = get_visitor()
    p = Path('/' + filepath)
    if not p.exists():
        return Response(f'Not found: {filepath}', status=404)
    try:
        p.resolve().relative_to(BASE_DIR.resolve())
    except ValueError:
        return Response('Access denied', status=403)
    if not is_path_allowed(str(p), visitor["ring"]):
        return Response('Access denied', status=403)
    mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
    # Figma-style element comments ride along on served .html (serve-time only)
    if p.suffix.lower() in ('.html', '.htm'):
        try:
            html = _inject_element_comments(p.read_text(errors='replace'), p.resolve())
            return Response(html, content_type='text/html; charset=utf-8')
        except Exception:
            pass
    return Response(p.read_bytes(), content_type=mime)


@app.route('/browse')
@app.route('/browse/<path:filepath>')
def serve_browse(filepath=''):
    visitor = get_visitor()
    file_path = '/' + filepath if filepath else str(BASE_DIR)
    p = Path(file_path)

    if not p.exists():
        return Response(f'Not found: {file_path}', status=404)

    # Security: must be under BASE_DIR
    try:
        p.resolve().relative_to(BASE_DIR.resolve())
    except ValueError:
        return Response('Access denied', status=403)

    # Tailscale identity-based access control
    if not is_path_allowed(str(p), visitor["ring"]):
        return Response('Access denied', status=403)

    if p.is_dir():
        return _serve_directory(p, visitor)
    else:
        return _serve_file(p)


def _serve_directory(p, visitor=None):
    visitor = visitor or get_visitor()
    ring = visitor["ring"]
    entries = []
    try:
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name in SKIP_DIRS:
                continue
            if item.name.startswith('.') and item.name not in ('.claude',):
                continue
            # Filter out restricted paths for this visitor
            if not is_path_allowed(str(item), ring):
                continue
            try:
                stat = item.stat()
                entries.append({
                    'name': item.name,
                    'is_dir': item.is_dir(),
                    'size': stat.st_size if not item.is_dir() else 0,
                    'mtime': stat.st_mtime,
                    'path': str(item),
                })
            except (PermissionError, OSError):
                continue
    except PermissionError:
        return Response('Permission denied', status=403)

    # Check if this is the diary folder
    is_diary = str(p).rstrip('/').endswith('/diary')

    rows = []
    for e in entries:
        icon = FILE_TYPE_SVGS.get('_folder', '') if e['is_dir'] else _file_icon_svg(e['name'])
        size = "" if e['is_dir'] else human_size(e['size'])
        date = smart_date(e['mtime'])

        # Diary special treatment: show human-readable dates
        display_name = e['name']
        extra_class = ''
        if is_diary and re.match(r'^\d{4}-\d{2}-\d{2}\.md$', e['name']):
            try:
                dt = datetime.strptime(e['name'][:10], '%Y-%m-%d')
                display_name = dt.strftime('%A, %B %-d, %Y')
                extra_class = ' diary-date'
            except ValueError:
                pass

        name_html = f'<a href="/browse{e["path"]}" class="{extra_class}">{display_name}</a>'
        name_attr = html_mod.escape(e['name'], quote=True)
        rows.append(f'''<tr data-name="{name_attr}" data-size="{e['size']}" data-mtime="{e['mtime']}" data-isdir="{1 if e['is_dir'] else 0}">
            <td><div class="name"><span class="icon">{icon}</span>{name_html}</div></td>
            <td class="size">{size}</td>
            <td class="date">{date}</td>
        </tr>''')

    # Hero section for home page
    hero_html = ''
    if str(p) == str(BASE_DIR):
        hero_html = _home_hero()

    # Slim filter/sort control row — only for directories with 8+ entries
    controls_html = ''
    if len(entries) >= 8:
        controls_html = (
            '<div class="listing-controls" data-dirkey="' + html_mod.escape(str(p), quote=True) + '">'
            '<input class="listing-filter" type="text" placeholder="filter…" '
            'spellcheck="false" autocomplete="off">'
            '<div class="listing-sort">'
            '<button class="sort-btn" data-key="name">name</button>'
            '<button class="sort-btn" data-key="size">size</button>'
            '<button class="sort-btn" data-key="modified">modified</button>'
            '<span class="listing-count"></span>'
            '</div>'
            '</div>'
        )

    content = f'''{hero_html}<div class="listing">{controls_html}<table>
        <tbody>{"".join(rows)}</tbody>
    </table></div>'''

    return _render_page(str(p), content)


def _serve_file(p):
    ext = p.suffix.lower()

    # For images, serve raw
    if ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'):
        mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
        return Response(p.read_bytes(), content_type=mime)

    # For text files, render in the explorer
    if ext in TEXT_EXTENSIONS or ext == '':
        try:
            text = p.read_text(errors='replace')
        except Exception as e:
            return Response(str(e), status=500)

        if ext == '.md':
            escaped = html_mod.escape(text)
            # For <script type="text/plain">, content is raw text (browser won't decode entities),
            # so we use the original text, only escaping </script> to prevent tag closure.
            raw_for_script = text.replace('</script>', '<\\/script>')
            is_editable = True
            edit_button = f'<button id="btn-edit" class="btn-edit" data-path="{html_mod.escape(str(p))}" data-mtime="{p.stat().st_mtime}">Edit</button>' if is_editable else ''
            edit_area = '''<div id="edit-area" style="display:none;">
                <div class="edit-bar" style="margin-bottom:12px; justify-content:flex-end;">
                    <span id="conflict-warning" style="display:none; align-items:center; gap:10px; margin-right:auto; font-family:'JetBrains Mono',monospace; font-size:12px; color:#BF616A;">
                        <span>File changed on disk.</span>
                        <button id="btn-overwrite" type="button" style="background:none; border:none; color:#BF616A; font-family:'JetBrains Mono',monospace; font-size:12px; text-decoration:underline; cursor:pointer; padding:0;">Overwrite anyway</button>
                        <button id="btn-reload" type="button" style="background:none; border:none; color:#BF616A; font-family:'JetBrains Mono',monospace; font-size:12px; text-decoration:underline; cursor:pointer; padding:0;">Reload file</button>
                    </span>
                    <span id="save-status" class="save-status"></span>
                    <button id="btn-cancel" class="btn-cancel">Cancel</button>
                    <button id="btn-save" class="btn-save">Save</button>
                </div>
                <div id="cm-editor"></div>
            </div>''' if is_editable else ''
            content = f'''<div class="file-content">
                <div class="edit-bar">
                    <span class="filename" style="margin-bottom:0; padding-bottom:0; border-bottom:none;">{p.name} &middot; {human_size(p.stat().st_size)}</span>
                    {edit_button}
                </div>
                <script id="markdown-raw" type="text/plain">{raw_for_script}</script>
                <div id="markdown-rendered" class="markdown-body"></div>
                {edit_area}
            </div>'''
        elif ext == '.html':
            lang = lang_for_ext(ext)
            escaped = html_mod.escape(text)
            raw_url = f'/raw{p}'
            content = f'''<div class="file-content">
                <div class="filename" style="display:flex; align-items:center; gap:12px;">
                    {p.name} &middot; {human_size(p.stat().st_size)}
                    <div style="display:inline-flex; border:1px solid var(--border); border-radius:6px; overflow:hidden; font-size:12px; margin-left:auto;">
                        <button id="btn-render" onclick="toggleHtmlView('render')" style="padding:4px 12px; background:var(--accent); color:var(--bg-primary); border:none; cursor:pointer; font-family:var(--font-mono); font-size:12px;">Render</button>
                        <button id="btn-code" onclick="toggleHtmlView('code')" style="padding:4px 12px; background:transparent; color:var(--text-secondary); border:none; cursor:pointer; font-family:var(--font-mono); font-size:12px;">Code</button>
                    </div>
                </div>
                <div id="html-render-view">
                    <iframe src="{raw_url}" style="width:100%; height:80vh; border:1px solid var(--border-subtle); border-radius:6px; background:#fff;"></iframe>
                </div>
                <div id="html-code-view" style="display:none;">
                    <div class="code-body"><pre><code class="language-{lang}">{escaped}</code></pre></div>
                </div>
            </div>
            <script>
            function toggleHtmlView(mode) {{
                var renderView = document.getElementById('html-render-view');
                var codeView = document.getElementById('html-code-view');
                var btnRender = document.getElementById('btn-render');
                var btnCode = document.getElementById('btn-code');
                if (mode === 'render') {{
                    renderView.style.display = '';
                    codeView.style.display = 'none';
                    btnRender.style.background = 'var(--accent)';
                    btnRender.style.color = 'var(--bg-primary)';
                    btnCode.style.background = 'transparent';
                    btnCode.style.color = 'var(--text-secondary)';
                }} else {{
                    renderView.style.display = 'none';
                    codeView.style.display = '';
                    btnCode.style.background = 'var(--accent)';
                    btnCode.style.color = 'var(--bg-primary)';
                    btnRender.style.background = 'transparent';
                    btnRender.style.color = 'var(--text-secondary)';
                    if (typeof hljs !== 'undefined') hljs.highlightAll();
                }}
            }}
            </script>'''
        else:
            lang = lang_for_ext(ext)
            escaped = html_mod.escape(text)
            content = f'''<div class="file-content">
                <div class="filename">{p.name} &middot; {human_size(p.stat().st_size)}</div>
                <div class="code-body"><pre><code class="language-{lang}">{escaped}</code></pre></div>
            </div>'''

        return _render_page(str(p), content)

    # Binary files: download
    mime = mimetypes.guess_type(str(p))[0] or 'application/octet-stream'
    return Response(
        p.read_bytes(),
        content_type=mime,
        headers={'Content-Disposition': f'attachment; filename="{p.name}"'}
    )


# ============================================================
# MODELS — which mind answers in which room
# ============================================================
# The Slack bot reads MODEL_CONFIG_FILE fresh on every claude spawn (see
# resolve_model_settings in bot.py). This page is the only editor.

MODEL_CONFIG_FILE = BOT_DIR / 'model-config.json'
MODEL_CONFIG_HISTORY = MODEL_CONFIG_FILE.parent / '.model-config-history'
SLACK_BOT_ENV = MODEL_CONFIG_FILE.parent / '.env'
EFFORT_LEVELS = ['low', 'medium', 'high', 'xhigh', 'max']
_MODEL_ID_RE = re.compile(r'^[A-Za-z0-9._\-\[\]]{1,80}$')
_SLACK_CHANNEL_RE = re.compile(r'^[CDG][A-Z0-9]{6,}$')
_SLACK_USER_RE = re.compile(r'^U[A-Z0-9]{6,}$')
_slack_channels_cache = {'at': 0.0, 'channels': None, 'error': ''}
_SLACK_CHANNELS_TTL = 600


def _model_config_read():
    """(config dict, sha256 of the raw file). Missing file → empty config, sha ''."""
    try:
        raw = MODEL_CONFIG_FILE.read_bytes()
    except FileNotFoundError:
        return {}, ''
    try:
        cfg = json.loads(raw)
    except Exception:
        cfg = {}
    return cfg, hashlib.sha256(raw).hexdigest()


def _settings_default_model():
    try:
        return json.loads((Path.home() / '.claude' / 'settings.json').read_text()).get('model', '') or ''
    except Exception:
        return ''


def _validate_model_config(cfg):
    """Return an error string, or '' when the shape is sound."""
    if not isinstance(cfg, dict):
        return 'config must be an object'
    if cfg.get('default_effort') not in EFFORT_LEVELS:
        return 'default_effort must be one of ' + ', '.join(EFFORT_LEVELS)
    dm = cfg.get('default_model', '')
    if dm and (not isinstance(dm, str) or not _MODEL_ID_RE.match(dm)):
        return f'bad default_model {dm!r}'
    models = cfg.get('models')
    if not isinstance(models, list) or not all(isinstance(m, str) and _MODEL_ID_RE.match(m) for m in models):
        return 'models must be a list of model ids'
    for section, key_re in (('channels', _SLACK_CHANNEL_RE), ('dm_users', _SLACK_USER_RE)):
        entries = cfg.get(section, {})
        if not isinstance(entries, dict):
            return f'{section} must be an object'
        for k, v in entries.items():
            if not key_re.match(k):
                return f'{section}: bad Slack id {k!r}'
            if not isinstance(v, dict):
                return f'{section}.{k} must be an object'
            m = v.get('model', '')
            if m and (not isinstance(m, str) or not _MODEL_ID_RE.match(m)):
                return f'{section}.{k}: bad model {m!r}'
            e = v.get('effort', '')
            if e and e not in EFFORT_LEVELS:
                return f'{section}.{k}: bad effort {e!r}'
    prompts = cfg.get('model_prompts', {})
    if not isinstance(prompts, dict):
        return 'model_prompts must be an object'
    for m, text in prompts.items():
        if not isinstance(text, str):
            return f'model_prompts.{m} must be text'
        if len(text) > 20000:
            return f'model_prompts.{m}: over 20,000 characters'
    return ''


def save_model_config(cfg, expected_sha):
    """Validate, back up, write atomically. Returns (ok, payload)."""
    err = _validate_model_config(cfg)
    if err:
        return False, {'error': err}
    _, current_sha = _model_config_read()
    if expected_sha != current_sha:
        return False, {'error': 'config changed underneath you — reload the page', 'stale': True}
    # keep the readme + key order stable so the file stays pleasant to read by hand
    ordered = OrderedDict()
    for k in ('_readme', 'default_model', 'default_effort', 'models', 'channels', 'dm_users', 'model_prompts'):
        if k in cfg:
            ordered[k] = cfg[k]
    for k, v in cfg.items():
        ordered.setdefault(k, v)
    # drop empty entries so the file doesn't fill with {} rows
    for section in ('channels', 'dm_users'):
        ordered[section] = {k: v for k, v in ordered.get(section, {}).items()
                            if any(v.get(f) for f in ('model', 'effort'))}
    ordered['model_prompts'] = {k: v for k, v in ordered.get('model_prompts', {}).items() if v.strip()}
    text = json.dumps(ordered, indent=2, ensure_ascii=False) + '\n'
    try:
        MODEL_CONFIG_HISTORY.mkdir(exist_ok=True)
        if MODEL_CONFIG_FILE.exists():
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            shutil.copy2(MODEL_CONFIG_FILE, MODEL_CONFIG_HISTORY / f'model-config-{stamp}.json')
        tmp = MODEL_CONFIG_FILE.with_suffix('.json.tmp')
        tmp.write_text(text)
        os.replace(tmp, MODEL_CONFIG_FILE)
    except Exception as e:
        return False, {'error': f'write failed: {e}'}
    return True, {'sha': hashlib.sha256(text.encode()).hexdigest()}


def _slack_bot_token():
    try:
        for line in SLACK_BOT_ENV.read_text().splitlines():
            if line.startswith('SLACK_BOT_TOKEN='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ''


def _slack_bot_channels():
    """[{id, name, kind}] for every channel the bot is a member of. Cached 10 min.
    Uses urllib against users.conversations — no slack_sdk in this interpreter."""
    now = time.time()
    if _slack_channels_cache['channels'] is not None and now - _slack_channels_cache['at'] < _SLACK_CHANNELS_TTL:
        return _slack_channels_cache['channels'], _slack_channels_cache['error']
    token = _slack_bot_token()
    channels, error = [], ''
    if not token:
        error = 'no SLACK_BOT_TOKEN in the bot .env'
    else:
        import urllib.request
        cursor = ''
        try:
            while True:
                q = urllib.parse.urlencode({'types': 'public_channel,private_channel',
                                            'exclude_archived': 'true', 'limit': 200, 'cursor': cursor})
                req = urllib.request.Request('https://slack.com/api/users.conversations?' + q,
                                             headers={'Authorization': f'Bearer {token}'})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.loads(r.read().decode())
                if not data.get('ok'):
                    error = f"slack: {data.get('error', 'unknown error')}"
                    break
                for c in data.get('channels', []):
                    channels.append({'id': c['id'], 'name': '#' + c.get('name', c['id']),
                                     'kind': 'private' if c.get('is_private') else 'public'})
                cursor = (data.get('response_metadata') or {}).get('next_cursor') or ''
                if not cursor:
                    break
        except Exception as e:
            error = f'slack unreachable: {e}'
    if channels or not error:
        channels.sort(key=lambda c: c['name'].lower())
        _slack_channels_cache.update(at=now, channels=channels, error=error)
        return channels, error
    # keep serving the last good list if Slack is flaky
    if _slack_channels_cache['channels'] is not None:
        return _slack_channels_cache['channels'], error
    return [], error


def _models_page_data():
    cfg, sha = _model_config_read()
    cfg.setdefault('default_effort', 'medium')
    cfg.setdefault('models', [])
    cfg.setdefault('channels', {})
    cfg.setdefault('dm_users', {})
    cfg.setdefault('model_prompts', {})
    channels, slack_err = _slack_bot_channels()
    channels = list(channels)
    seen = {c['id'] for c in channels}
    # config may reference rooms the bot has since left, or Slack may be down — still show them
    for cid, entry in cfg['channels'].items():
        if cid not in seen:
            channels.append({'id': cid, 'name': entry.get('name') or cid, 'kind': 'unlisted'})
    # every model in play is a dropdown option (and gets a prompt slot) even if someone typed it by hand
    # into the file — including whichever model answers wherever nothing is set: the bot's own
    # default_model when it names one, else the Mac-wide settings.json model
    editable_default = bool(cfg.get('default_model'))
    default_model = cfg.get('default_model') or _settings_default_model()
    models = list(cfg['models'])
    for entry in list(cfg['channels'].values()) + list(cfg['dm_users'].values()):
        m = entry.get('model')
        if m and m not in models:
            models.append(m)
    for m in list(cfg['model_prompts']) + ([default_model] if default_model else []):
        if m not in models:
            models.append(m)
    cfg['models'] = models
    people = list(MODELS_DM_USERS)
    seen_people = {p['id'] for p in people}
    for uid, dm_entry in cfg['dm_users'].items():
        if uid not in seen_people:
            people.append({'id': uid, 'name': dm_entry.get('name') or uid})
    return {'config': cfg, 'sha': sha, 'channels': channels, 'people': people,
            'default_model': default_model, 'default_model_editable': editable_default,
            'efforts': EFFORT_LEVELS, 'slack_error': slack_err}


_MODELS_JS = r"""
(function(){
  const D = window.MODELS_DATA; let cfg = D.config; let sha = D.sha;
  const $ = (s, r) => (r||document).querySelector(s);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  // the Default row above says what "default" is; repeating the id here only truncated it
  // picking the model that already is the default is the default — no pinned copies, nothing to light up
  const pick = m => (m === D.default_model ? '' : m);

  function modelSelect(current){
    let h = '<select data-field="model" class="' + (!current ? 'inherit' : '') + '">';
    h += '<option value="">default</option>';
    for (const m of cfg.models) if (m !== D.default_model) h += '<option value="' + esc(m) + '"' + (m===current?' selected':'') + '>' + esc(m) + '</option>';
    return h + '</select>';
  }
  function effortSelect(current){
    let h = '<select data-field="effort" class="' + (!current ? 'inherit' : '') + '">';
    h += '<option value="">default</option>';
    for (const e of D.efforts) h += '<option value="' + e + '"' + (e===current?' selected':'') + '>' + e + '</option>';
    return h + '</select>';
  }
  // the Slack id lives in the tooltip only — nobody picks a model by id
  function row(section, id, name, note){
    const e = (cfg[section][id] || {});
    return '<div class="models-row" data-section="' + section + '" data-id="' + esc(id) + '">'
      + '<div class="models-name" title="' + esc(name + ' · ' + id) + '">' + esc(name)
      + (note ? ' <span class="note">· ' + esc(note) + '</span>' : '') + '</div>'
      + modelSelect(pick(e.model || '')) + effortSelect(e.effort || '') + '</div>';
  }
  // {used: bool, text: 'where this model answers'} — where it is set by hand, then where it lands by default
  function whereUsed(m){
    const set = [];
    for (const c of D.channels) if (pick((cfg.channels[c.id]||{}).model || '') === m) set.push(c.name);
    for (const p of D.people) if (pick((cfg.dm_users[p.id]||{}).model || '') === m) set.push(p.name + "'s DM");
    const places = set.length ? ['set in ' + set.join(', ')] : [];
    if (m === D.default_model) {
      const n = D.channels.filter(c => !pick((cfg.channels[c.id]||{}).model || '')).length;
      const dms = D.people.filter(p => !pick((cfg.dm_users[p.id]||{}).model || '')).map(p => p.name + "'s DM");
      const parts = (n ? [n + ' channel' + (n===1?'':'s')] : []).concat(dms);
      if (parts.length) places.push('default for ' + parts.join(' + '));
    }
    return {used: places.length > 0, text: places.length ? esc(places.join(' · ')) : 'not in use anywhere'};
  }
  // only a model nothing answers as can be removed (the settings.json default never); the label says when a prompt goes with it
  function removeLink(m, info){
    if (info.used || m === D.default_model) return '';
    const label = 'remove from dropdowns' + (cfg.model_prompts[m] ? ' — deletes its prompt' : '');
    return '<button class="steer-link" data-act="remove-model" data-model="' + esc(m) + '">' + label + '</button>';
  }
  const promptFoot = (m, info) => removeLink(m, info);
  function promptBlock(m, info){
    const t = cfg.model_prompts[m] || '';
    return '<div class="models-prompt" data-model="' + esc(m) + '">'
      + '<div class="models-prompt-head"><span class="model">' + esc(m) + '</span>'
      + '<span class="where">' + info.text + '</span></div>'
      + '<textarea spellcheck="true" placeholder="Plain text, added after CLAUDE.md whenever this model answers. Say what it needs that CLAUDE.md does not cover, e.g. &quot;Keep Slack replies to a few lines — you tend to over-explain.&quot; Saves as you type.">' + esc(t) + '</textarea>'
      + '<div class="models-prompt-foot">' + promptFoot(m, info) + '</div></div>';
  }
  // re-render prompts without touching a textarea someone may be typing in
  function renderPrompts(){
    const box = $('#models-prompts');
    const keep = {};
    for (const b of box.querySelectorAll('.models-prompt')) keep[b.dataset.model] = b;
    box.innerHTML = '';
    for (const m of cfg.models) {
      const info = whereUsed(m);
      const old = keep[m];
      if (old && $('textarea', old)) {
        $('.where', old).innerHTML = info.text;
        $('.models-prompt-foot', old).innerHTML = promptFoot(m, info);
        box.appendChild(old);
      }
      else box.insertAdjacentHTML('beforeend', promptBlock(m, info));
    }
  }
  function render(){
    $('#models-channels').innerHTML = D.channels.map(c => row('channels', c.id, c.name, c.kind==='unlisted' ? 'not a member' : '')).join('')
      || '<div class="health-empty">' + esc(D.slack_error || 'the bot is in no channels') + '</div>';
    $('#models-people').innerHTML = D.people.map(p => row('dm_users', p.id, p.name, '')).join('');
    renderPrompts();
    $('#models-default-effort').innerHTML = D.efforts.map(e => '<option' + (e===cfg.default_effort?' selected':'') + '>' + e + '</option>').join('');
    // present only when the bot names its own default; otherwise the default is
    // ~/.claude/settings.json, which this page does not own
    const dm = $('#models-default-model');
    if (dm) dm.innerHTML = cfg.models.map(m => '<option' + (m===D.default_model?' selected':'') + '>' + esc(m) + '</option>').join('');
  }
  // one status line for every save on the page: "saved" flashes, an error stays until the next save
  const status = $('#models-status');
  let statusTimer;
  function flash(text, err){
    clearTimeout(statusTimer);
    status.textContent = text; status.className = 'models-saved models-status ' + (err ? 'err' : 'show');
    if (!err) statusTimer = setTimeout(() => { status.className = 'models-saved models-status'; }, 1600);
  }
  let saving = Promise.resolve();
  function save(){
    saving = saving.then(async () => {
      const r = await fetch('/models', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({config: cfg, sha})});
      const j = await r.json().catch(() => ({error:'bad response'}));
      if (!r.ok) {
        flash(j.error || 'save failed', true);
        if (j.stale) setTimeout(() => location.reload(), 1200);
        return false;
      }
      sha = j.sha; flash('saved');
      return true;
    });
    return saving;
  }
  // prompts autosave like everything else: shortly after typing pauses, and the moment the box loses focus
  const promptTimers = new Map();
  function queuePrompt(blk, delay){
    const m = blk.dataset.model;
    clearTimeout(promptTimers.get(m));
    promptTimers.set(m, setTimeout(() => {
      promptTimers.delete(m);
      const ta = $('textarea', blk); if (!ta) return;
      if ((cfg.model_prompts[m] || '') !== ta.value) {
        cfg.model_prompts[m] = ta.value;
        $('.models-prompt-foot', blk).innerHTML = promptFoot(m, whereUsed(m));   // remove-link label tracks whether a prompt exists
        save();
      }
    }, delay));
  }
  document.addEventListener('input', ev => {
    const blk = ev.target.closest('.models-prompt');
    if (blk && ev.target.tagName === 'TEXTAREA') queuePrompt(blk, 800);
  });
  document.addEventListener('focusout', ev => {
    const blk = ev.target.closest('.models-prompt');
    if (blk && ev.target.tagName === 'TEXTAREA') queuePrompt(blk, 0);
  });
  document.addEventListener('change', ev => {
    const sel = ev.target;
    const r = sel.closest('.models-row');
    if (r && sel.dataset.field) {
      const sec = r.dataset.section, id = r.dataset.id;
      cfg[sec][id] = cfg[sec][id] || {};
      cfg[sec][id][sel.dataset.field] = sel.value;
      sel.classList.toggle('inherit', !sel.value);
      save().then(renderPrompts);
      return;
    }
    if (sel.id === 'models-default-effort') { cfg.default_effort = sel.value; save().then(render); return; }
    // moving the default moves every room that inherits it, so the whole page re-reads it
    if (sel.id === 'models-default-model') { cfg.default_model = sel.value; D.default_model = sel.value; save().then(render); }
  });
  document.addEventListener('click', ev => {
    const b = ev.target.closest('[data-act]'); if (!b) return;
    const act = b.dataset.act;
    if (act === 'add-model') {
      const inp = $('#models-add-input'); const m = inp.value.trim();
      const note = $('#models-add-saved');
      if (!/^[A-Za-z0-9._\-\[\]]{1,80}$/.test(m)) { note.textContent = 'model ids look like claude-fable-5 or claude-opus-4-8[1m]'; note.className='models-saved err'; return; }
      if (cfg.models.includes(m)) { note.textContent = 'already listed'; note.className='models-saved err'; return; }
      cfg.models.push(m); inp.value = ''; note.className = 'models-saved';
      save().then(render);
    }
    if (act === 'remove-model') {
      const m = b.dataset.model;
      if (!confirm('Remove ' + m + ' from the dropdowns?' + (cfg.model_prompts[m] ? ' Its prompt is deleted too.' : ''))) return;
      cfg.models = cfg.models.filter(x => x !== m); delete cfg.model_prompts[m];
      save().then(render);
    }
  });
  document.getElementById('models-add-input').addEventListener('keydown', ev => {
    if (ev.key === 'Enter') { ev.preventDefault(); document.querySelector('[data-act="add-model"]').click(); }
  });
  render();
})();
"""


@app.route('/models')
def serve_models():
    """Which model and effort answers in each Slack channel and DM, and what each model is told."""
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return Response('Access denied — supervisors only', status=403)
    data = _models_page_data()
    default_model = data['default_model'] or '(none in settings.json)'
    slack_note = ''
    if data['slack_error']:
        slack_note = ('<div class="steer-note">channel list: ' + html_mod.escape(data['slack_error'])
                      + ' — showing channels from the config file only</div>')
    if data['default_model_editable']:
        default_cell = ('<div class="fixed" id="models-default-model-cell">'
                        '<select id="models-default-model"></select></div>')
    else:
        settings_path = str(Path.home() / '.claude' / 'settings.json')
        default_cell = (f'<div class="fixed">{html_mod.escape(default_model)}'
                        f'<div class="why"><a class="steer-link" href="/browse{settings_path}">change in '
                        '~/.claude/settings.json</a> &mdash; it&rsquo;s the Claude default for the '
                        'whole Mac, not just the bot. Name a <code>default_model</code> in '
                        'model-config.json to pick it here instead.</div></div>')
    payload = json.dumps(data).replace('</', '<\\/')
    content = MODELS_PAGE_HTML.replace('__CONFIG_PATH__', str(MODEL_CONFIG_FILE)) \
        .replace('__HISTORY_PATH__', str(MODEL_CONFIG_HISTORY)) \
        .replace('__DEFAULT_CELL__', default_cell) \
        .replace('__SLACK_NOTE__', slack_note) \
        .replace('__DATA__', payload) \
        .replace('__JS__', _MODELS_JS)
    return _render_page('Models', content)


MODELS_PAGE_HTML = '''<div class="models-page">
    <h1>Models</h1>
    <div class="subtitle">Which Claude model answers in each Slack channel and DM. Changes save on their own; new threads pick them up right away, open threads on their next reply.</div>
    __SLACK_NOTE__
    <div class="models-section default">
      <div class="models-section-label cols"><span>Default</span><span class="col">model</span><span class="col">effort</span></div>
      <div class="models-row default">
        <div class="models-name" title="every channel and DM with no setting of its own">unless set below</div>
        __DEFAULT_CELL__
        <select id="models-default-effort"></select>
      </div>
    </div>
    <div class="models-section">
      <div class="models-section-label"><span>Channels</span></div>
      <div id="models-channels"></div>
    </div>
    <div class="models-section">
      <div class="models-section-label"><span>Direct messages</span></div>
      <div id="models-people"></div>
    </div>
    <div class="models-section">
      <div class="models-section-label"><span>Models &amp; prompts</span><span class="hint">the dropdown options &middot; a prompt goes after CLAUDE.md</span></div>
      <div id="models-prompts"></div>
      <div class="models-add">
        <input type="text" id="models-add-input" placeholder="add a model id" spellcheck="false">
        <button class="steer-btn" data-act="add-model">Add</button>
        <span class="models-saved" id="models-add-saved" style="grid-column:1/-1;text-align:left"></span>
      </div>
    </div>
    <div class="models-foot">Stored in <a href="/browse__CONFIG_PATH__">model-config.json</a> (<a href="/browse__HISTORY_PATH__">history</a>).</div>
    <div class="models-saved models-status" id="models-status"></div>
</div>
<script>window.MODELS_DATA = __DATA__;</script>
<script>__JS__</script>'''


@app.route('/models', methods=['POST'])
def save_models():
    visitor = get_visitor()
    if visitor["ring"] > 1:
        return Response('Access denied — supervisors only', status=403)
    body = request.get_json(silent=True) or {}
    ok, payload = save_model_config(body.get('config'), body.get('sha', ''))
    if not ok:
        return jsonify(payload), (409 if payload.get('stale') else 400)
    return jsonify(payload)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    from waitress import serve
    print(f"File Explorer running on port {PORT}")
    print(f"  Base directory: {BASE_DIR}")
    if TASK_PREFIXES:
        print(f"  Monitoring tasks: {', '.join(TASK_PREFIXES)}")
    serve(app, host="0.0.0.0", port=PORT, threads=8)
