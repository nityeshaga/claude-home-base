# Brief Delivery

How to format, deliver, and archive the brief — then reset the notepad for the next cycle.

## Delivery Process

1. **Read brief preferences** from `${CLAUDE_PLUGIN_DATA}/brief-preferences-{user}.md`
2. **Snapshot the notepad** — take the current state of `~/brief-{user}.md`
3. **Format it** according to the user's delivery preferences (HTML, markdown, Slack message, etc.). Apply the personality — the delivered brief is where the Alfred voice comes through. The notepad is operational; the delivered brief is the polished output.
4. **Archive it** — save the delivered brief to `~/briefs/{user}/{DATE}.md` (or `.html`, matching the format). Create the directory if it doesn't exist.
5. **Deliver it** via the user's preferred channel (Slack DM, email, file link, etc.)
6. **Deliver exactly once.** If a send call errors, times out, or returns ambiguously, do NOT retry blindly — a timeout is not proof of failure. First check the channel for a message posted since the run started (e.g. Slack `conversations_history`); only re-send if nothing actually landed. Blind retries deliver the same brief two or three times, which reads as spam in the one channel the user asked to trust.

## Brief Preferences

Stored in `${CLAUDE_PLUGIN_DATA}/brief-preferences-{user}.md`. Controls the output format and delivery channel — completely separate from what goes *into* the brief.

Sections:

- **Delivery Method** — how the brief reaches the user (HTML page with link, markdown file, email, Slack DM, etc.)
- **Delivery Style** — tone and density (concise action-first, conversational catchup, formal executive summary, etc.)
- **Brief Structure** — preferred ordering of sections in the delivered brief
- **Delivery Timing** — when briefs should be delivered (relevant for scheduled automation)

This file is calibrated during onboarding (see `handbook/new-user-onboarding.md`) and updated whenever the user gives feedback on how briefs are delivered.

## Sign-Off

End the delivered brief — both the archived page footer and the Slack message that delivers it — with one quiet closing line, adapted to the user's tone preferences:

> Just reply if you want me to brief you differently — I'll use the briefing skill to save your preferences.

This line is user-facing on purpose: it invites feedback, and because it travels in the Slack thread, any future session handling a reply sees in-context which skill owns brief preferences. Do not replace it with a "note to self" — text addressed to yourself at the end of a delivery session evaporates when the session ends.
