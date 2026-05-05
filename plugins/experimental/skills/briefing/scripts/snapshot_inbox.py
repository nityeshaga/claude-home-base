#!/usr/bin/env python3
"""
Snapshot the current inbox state for before/after diffing.

Usage:
    python3 snapshot_inbox.py before    # saves /tmp/inbox_before_emails.json + /tmp/inbox_before_snapshot.txt
    python3 snapshot_inbox.py after     # saves /tmp/inbox_after_emails.json + /tmp/inbox_after_snapshot.txt
    python3 snapshot_inbox.py diff      # prints what changed between before and after
"""

import json
import subprocess
import sys


def fetch_inbox(max_results=50):
    """Fetch inbox message IDs and metadata.

    Tries category:primary first (for users with tabbed inbox).
    Falls back to in:inbox if no results (tabs not enabled).
    """
    result = subprocess.run(
        ['gws', 'gmail', 'users', 'messages', 'list', '--params',
         json.dumps({"userId": "me", "q": "in:inbox category:primary", "maxResults": max_results})],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    ids = [m['id'] for m in data.get('messages', [])]

    if not ids:
        result = subprocess.run(
            ['gws', 'gmail', 'users', 'messages', 'list', '--params',
             json.dumps({"userId": "me", "q": "in:inbox", "maxResults": max_results})],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        ids = [m['id'] for m in data.get('messages', [])]

    emails = []
    for msg_id in ids:
        r = subprocess.run(
            ['gws', 'gmail', 'users', 'messages', 'get', '--params',
             json.dumps({"userId": "me", "id": msg_id, "format": "metadata",
                         "metadataHeaders": ["From", "Subject", "Date"]})],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            d = json.loads(r.stdout)
            headers = {h['name']: h['value'] for h in d.get('payload', {}).get('headers', [])}
            labels = d.get('labelIds', [])
            emails.append({
                'id': msg_id,
                'from': headers.get('From', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'unread': 'UNREAD' in labels
            })

    return emails


def save_snapshot(emails, label):
    """Save JSON + human-readable snapshot."""
    json_path = f'/tmp/inbox_{label}_emails.json'
    txt_path = f'/tmp/inbox_{label}_snapshot.txt'

    with open(json_path, 'w') as f:
        json.dump(emails, f, indent=2)

    lines = []
    for i, e in enumerate(emails):
        status = 'UNREAD' if e['unread'] else 'READ'
        lines.append(f"{i+1:2}. [{status}] {e['from'][:50]} | {e['subject'][:65]} | id:{e['id']}")

    with open(txt_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Saved {len(emails)} emails to {json_path} and {txt_path}")


def diff_snapshots():
    """Compare before and after snapshots. Print what was archived (removed from inbox)."""
    try:
        with open('/tmp/inbox_before_emails.json') as f:
            before = json.load(f)
        with open('/tmp/inbox_after_emails.json') as f:
            after = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Run 'snapshot_inbox.py before' and 'snapshot_inbox.py after' first.")
        sys.exit(1)

    before_ids = {e['id'] for e in before}
    after_ids = {e['id'] for e in after}

    archived_ids = before_ids - after_ids
    kept_ids = before_ids & after_ids
    new_ids = after_ids - before_ids

    archived = [e for e in before if e['id'] in archived_ids]
    kept = [e for e in before if e['id'] in kept_ids]

    print(f"\n=== INBOX DIFF ===")
    print(f"Before: {len(before)} emails")
    print(f"After:  {len(after)} emails")
    print(f"Archived: {len(archived)}")
    print(f"Kept: {len(kept)}")
    print(f"New (arrived during archiving): {len(new_ids)}")

    if archived:
        print(f"\n--- ARCHIVED ({len(archived)}) ---")
        for e in archived:
            print(f"  {e['from'][:50]} | {e['subject'][:65]}")

    if kept:
        print(f"\n--- KEPT ({len(kept)}) ---")
        for e in kept:
            print(f"  {e['from'][:50]} | {e['subject'][:65]}")

    # Save diff as JSON for Claude to read
    diff_data = {
        'archived': archived,
        'kept': kept,
        'new_arrived': len(new_ids),
        'summary': {
            'total_before': len(before),
            'total_after': len(after),
            'archived_count': len(archived),
            'kept_count': len(kept)
        }
    }
    with open('/tmp/inbox_diff.json', 'w') as f:
        json.dump(diff_data, f, indent=2)
    print(f"\nFull diff saved to /tmp/inbox_diff.json")


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('before', 'after', 'diff'):
        print("Usage: snapshot_inbox.py [before|after|diff]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd in ('before', 'after'):
        emails = fetch_inbox()
        save_snapshot(emails, cmd)
    elif cmd == 'diff':
        diff_snapshots()
