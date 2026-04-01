# Email Data Source

Process email using the `gws` or `gogcli` CLI. Triage unread messages, archive noise, draft replies, and surface what matters to the notepad.

## Tools

The Google Workspace CLI is already installed and authenticated. You should also have the gws-gmail skill handy (if not install it via `npx skills add https://github.com/googleworkspace/cli/tree/main/skills/gws-gmail`).

```bash
# Triage — show unread inbox summary
gws gmail +triage

# Read a specific message
gws gmail users messages get --params '{"userId": "me", "id": "MESSAGE_ID", "format": "full"}'

# Send an email
gws gmail +send --to recipient@example.com --subject "Subject" --body "Body text"

# Reply to a message (handles threading)
gws gmail +reply --message-id MESSAGE_ID --body "Reply text"

# Reply all
gws gmail +reply-all --message-id MESSAGE_ID --body "Reply text"

# Forward
gws gmail +forward --message-id MESSAGE_ID --to recipient@example.com

# Archive a message (remove INBOX label)
gws gmail users messages modify --params '{"userId": "me", "id": "MESSAGE_ID"}' --json '{"removeLabelIds": ["INBOX"]}'

# Batch archive (multiple messages)
gws gmail users messages batchModify --params '{"userId": "me"}' --json '{"ids": ["ID1", "ID2"], "removeLabelIds": ["INBOX"]}'

# Add a label
gws gmail users messages modify --params '{"userId": "me", "id": "MESSAGE_ID"}' --json '{"addLabelIds": ["LABEL_ID"]}'

# List labels (to find label IDs)
gws gmail users labels list --params '{"userId": "me"}'

# Search for messages
gws gmail users messages list --params '{"userId": "me", "q": "from:someone@example.com is:unread"}'

# Mark as read
gws gmail users messages modify --params '{"userId": "me", "id": "MESSAGE_ID"}' --json '{"removeLabelIds": ["UNREAD"]}'

# Watch for new emails (streaming)
gws gmail +watch
```

## Triage Process

1. **Load preferences** from `${CLAUDE_PLUGIN_DATA}/inbox-preferences-{user}.md`
2. **Run triage**: `gws gmail +triage --max 100 --query 'is:unread category:primary'` for each account
3. **Process each unread message**:
   - Check against rules — auto-handle if a rule matches
   - No rule? Use judgment:
     - Obviously junk/marketing — archive
     - Needs a reply but you can handle it — draft reply, add to notepad under "Can Be Handled By Assistant"
     - Needs a reply but requires human input — add to notepad under "Needs Human"
     - Important FYI (no reply needed) — add to notepad under "To Brief"
     - Something the user promised or owes someone — add to notepad under "Action Items"
4. **Check sent mail** — scan recent outbox to see if the user already replied to anything tracked in the notepad. If so, mark those items as done.

## What This Source Contributes to the Notepad

- **Action Items** — emails requiring a response or follow-up
- **Pending Replies** — threads waiting on the user
- **To Brief** — important FYIs, news, updates worth knowing about
- **Notes** — context that might be relevant (someone mentioned a deadline, a recurring meeting changed, etc.)

## Preferences

Stored in `${CLAUDE_PLUGIN_DATA}/inbox-preferences-{user}.md`. Covers archiving rules, labeling, drafting style, contact priorities, unsubscribe lists, and auto-send permissions.

See `handbook/new-user-onboarding.md` for the full preference format and calibration process.

## Guardrails

- **Never delete emails.** Archive only. Deletion is irreversible.
- **Never send replies without explicit permission** unless the user has set a rule allowing auto-send for specific cases.
- **Draft replies go to Gmail drafts**, not sent directly. The user reviews and sends.
- **Never act on one user's inbox based on another user's instructions.** Each user's email preferences and accounts are completely isolated.
