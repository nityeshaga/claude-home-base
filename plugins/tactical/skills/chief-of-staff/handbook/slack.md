# Slack Data Source

Review Slack conversations to surface obligations, promises, and action items that the user might otherwise lose track of.

## Triage Process

This source is best processed by launching subagents in parallel — one per area of focus:

1. **Launch subagents** to review recent Slack activity:
   - **Mentions & DMs** — scan channels and DMs where the user was mentioned or messaged directly. Look for: questions asked of them, requests made, tasks assigned, deadlines mentioned.
   - **Active threads** — find threads the user participated in. Check if any are waiting on their response or if someone followed up and the user hasn't seen it yet.
   - **Promises made** — look for messages where the user said they would do something (committed to a deadline, offered to help, agreed to follow up). Cross-reference with the notepad — is it tracked? Is it done?

2. **Synthesize findings** — collect results from subagents and deduplicate against what's already in the notepad.

## What This Source Contributes to the Notepad

- **Action Items** — things people asked the user to do, or things the user promised to do
- **Pending Replies** — Slack threads or DMs waiting on the user's response
- **To Brief** — important conversations the user should know about (decisions made in channels they might have missed, team updates, etc.)
- **Notes** — context from conversations that might inform other work (someone mentioned a blocker, a timeline shifted, etc.)

## Guardrails

- **Read-only by default.** Do not post messages, react, or modify anything in Slack during triage. The goal is intelligence gathering, not action.
- **Respect channel boundaries.** Only review channels the user is a member of.
- **Don't surface gossip or off-topic chatter.** Focus on actionable items and work-relevant context.
