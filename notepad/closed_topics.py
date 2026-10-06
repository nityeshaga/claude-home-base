"""Closed topics: things a person said to stop raising.

Deleting an item does not make "never again" true. The item still sits in old
notes, the search index and whatever job produced it, and the next session that
reads one of those has no way to know it was closed. The ledger is the tombstone
a deletion forgets to leave: a markdown table, one row per closed topic.

    | date | user | match terms | their words |
    |---|---|---|---|
    | 2026-01-15 | alice | vendor + renewal | "That is settled. Stop bringing it up." |

Match terms are AND-ed, lowercased, and matched as substrings of one line. Keep
them narrow: two or three specific words beat one broad one. `user` is a person's
name, or `both` for everyone. To close a topic, append a row. Nothing is removed.
"""
import os
import re

LEDGER = os.path.expanduser("~/closed-items.md")

# A ledger row: | date | user | match terms | their words |
ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\w+)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$")

# A line that RECORDS the ban is not a breach of it. Naming the rule and raising
# the item read almost alike to a substring match, so the exemption is explicit.
RECORDING = re.compile(
    r"drop permanently|permanently[,:]? drop|do not re-?add|never re-?add|do-not-re-?add"
    r"|no longer (?:brief|raise)|stop (?:raising|bringing)|was killed|is closed|closed[- ]items"
    r"|excluded?|exclusions?|\bban\b|tombstone",
    re.I,
)


def load(path=LEDGER):
    """-> [(date, user, [terms], quote)]. A missing ledger closes nothing."""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        rows = f.readlines()
    for line in rows:
        m = ROW.match(line)
        if not m or m.group(1) == "date" or set(m.group(1)) <= set("-| "):
            continue
        terms = [t.strip().lower() for t in m.group(3).split("+") if t.strip()]
        if terms:
            out.append((m.group(1), m.group(2).lower(), terms, m.group(4)))
    return out


def hits(lines, entries, user):
    """-> [(index, quote)] for lines that re-raise a topic closed for user."""
    found = []
    for i, line in enumerate(lines):
        low = line.lower()
        if RECORDING.search(line):
            continue
        for _, u, terms, quote in entries:
            if u in (user, "both") and all(t in low for t in terms):
                found.append((i, quote))
                break
    return found
