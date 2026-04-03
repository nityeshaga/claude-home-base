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
import html as html_mod
import mimetypes
import urllib.parse
import plistlib
import subprocess
import re
import difflib
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
<title>DISPLAY_NAME_PLACEHOLDER</title>
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
  let cmEditor = null;

  function doSave() {
    if (!cmEditor) return;
    const content = cmEditor.getValue();
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    fetch('/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: filePath, content: content})
    }).then(r => r.json()).then(result => {
      if (result.ok) {
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
        }, 800);
      } else {
        status.textContent = 'Error: ' + result.error;
        status.style.color = '#f85149';
        status.style.display = 'inline';
      }
    }).catch(e => {
      status.textContent = 'Error: ' + e.message;
      status.style.color = '#f85149';
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
          'Cmd-S': function() { doSave(); },
          'Ctrl-S': function() { doSave(); },
          'Enter': 'newlineAndIndentContinueMarkdownList',
        },
      });
    } else {
      cmEditor.setValue(rawEl.textContent);
    }
    setTimeout(() => { cmEditor.refresh(); cmEditor.focus(); }, 10);
  });

  cancelBtn.addEventListener('click', () => {
    editArea.style.display = 'none';
    rendered.style.display = 'block';
    editBtn.style.display = 'inline-block';
  });

  saveBtn.addEventListener('click', doSave);
}
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


def _render_page(path_label, content, visitor=None):
    """Wrap content in the full HTML template with sidebar and breadcrumb."""
    visitor = visitor or get_visitor()
    page = HTML_TEMPLATE.replace('DISPLAY_NAME_PLACEHOLDER', DISPLAY_NAME)
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


def list_conversation_sessions():
    """List all JSONL conversation sessions with metadata."""
    sessions = []
    if not CONVERSATIONS_DIR.exists():
        return sessions

    for f in CONVERSATIONS_DIR.glob('*.jsonl'):
        try:
            stat = f.stat()
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

            # Clean up the preview
            preview = first_user_msg
            # Strip common forwarding prefixes
            slack_prefix = re.match(
                r'You received this message .+? respond with exactly: SKIP\s*',
                preview, re.DOTALL
            )
            if slack_prefix:
                preview = preview[slack_prefix.end():]
            if preview and len(preview) > 300:
                preview = preview[:300]
            preview = preview.strip().replace('\n', ' ')[:100]

            sessions.append({
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
            })
        except Exception:
            continue

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

        file_path.write_text(data['content'])
        return jsonify(ok=True)
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

            rows.append(f'''<div class="conv-row" onclick="window.location='/conversations/{s['id']}'">
                {marker_svg}
                <span class="conv-time">{time_str}</span>
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

    content = f'''<div class="conv-index">
        <div class="conv-index-header">
            <h1>Conversations</h1>
            <div class="subtitle">{total} sessions</div>
        </div>
        <div class="conv-group-tabs">{"".join(tabs_html)}</div>
        {"".join(sections_html)}
    </div>
    {tab_js}'''

    return _render_page('Conversations', content)


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

    msgs_html = []
    for msg in render_msgs:
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

            msgs_html.append(f'''<div class="conv-message role-{role} conv-meta-msg">
                <details class="conv-skill-loaded">
                    <summary>
                        <span class="skill-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 1.5v11"/><path d="M3.5 5l3.5-3.5L10.5 5"/><path d="M2 8.5h10"/><path d="M4 11h6"/></svg></span>
                        {html_mod.escape(label)} <span class="skill-size">({size_note})</span>
                    </summary>
                    <div class="skill-body">{''.join(_render_conversation_block(b, i) for i, b in enumerate(msg['blocks']))}</div>
                </details>
            </div>''')
            continue

        blocks_html = []
        for i, block in enumerate(msg['blocks']):
            blocks_html.append(_render_conversation_block(block, i))

        msgs_html.append(f'''<div class="conv-message role-{role}">
            <div class="conv-role-label">{role_label} <span class="conv-ts">{ts_display}</span></div>
            {"".join(blocks_html)}
        </div>''')

    # "Load more" if truncated
    load_more = ''
    if total_msgs > max_initial:
        remaining = total_msgs - max_initial
        load_more = f'<a href="/conversations/{session_id}?limit={total_msgs}" class="conv-load-more">Load {remaining} more messages</a>'

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
            </div>
        </div>
        {"".join(msgs_html)}
        {load_more}
    </div>
    <script>
    // Render markdown in conversation text blocks
    document.querySelectorAll('.conv-markdown[data-raw]').forEach(function(el) {{
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
    </script>'''

    return _render_page(f'Conversation: {date_str}', content)


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
        rows.append(f'''<tr>
            <td><div class="name"><span class="icon">{icon}</span>{name_html}</div></td>
            <td class="size">{size}</td>
            <td class="date">{date}</td>
        </tr>''')

    # Hero section for home page
    hero_html = ''
    if str(p) == str(BASE_DIR):
        hero_html = _home_hero()

    content = f'''{hero_html}<div class="listing"><table>
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
            edit_button = f'<button id="btn-edit" class="btn-edit" data-path="{html_mod.escape(str(p))}">Edit</button>' if is_editable else ''
            edit_area = '''<div id="edit-area" style="display:none;">
                <div class="edit-bar" style="margin-bottom:12px; justify-content:flex-end;">
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
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    from waitress import serve
    print(f"File Explorer running on port {PORT}")
    print(f"  Base directory: {BASE_DIR}")
    if TASK_PREFIXES:
        print(f"  Monitoring tasks: {', '.join(TASK_PREFIXES)}")
    serve(app, host="0.0.0.0", port=PORT, threads=8)
