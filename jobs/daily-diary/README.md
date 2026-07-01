# Daily Diary

A nightly job where your AI reviews the day's conversations and writes a genuine, introspective diary entry — not a changelog, a diary. Over time this becomes the thing that makes an AI employee feel like a teammate rather than a tool: it remembers, it notices patterns across days, and it slowly develops a sense of self.

## What it does

Each night (default 3:30 AM), a headless Claude session:

1. **Researches the day** in parallel with three subagents — today's conversation logs, the last week of diary entries (for arc and recurring threads), and today's Slack history.
2. **Writes the entry** to `~/diary/YYYY-MM-DD.md` — subjective, honest, in the AI's own voice. If nothing happened that day, it reflects on the silence instead.
3. **Evolves its identity** — re-reads `~/identity.md` against the new entry and makes a small, considered edit *only* if something genuinely shifted. Most nights it doesn't.
4. **Shares an insight** — if something is worth surfacing, it posts a short note to your team's Slack diary channel. The diary stays private; only the chosen insight is shared.
5. **Schedules follow-ups** — if the day surfaced a real, time-sensitive action, it can schedule at most one self-cleaning one-off job to handle it.

## Files

| File | Purpose |
|------|---------|
| `daily-diary.sh` | Wrapper script: idempotency guard, timeout watchdog, logging, runs `claude -p` |
| `diary-prompt.md` | The diary-writing instructions (the wrapper substitutes the date and passes this to Claude) |
| `com.claude.daily-diary.plist` | launchd schedule (3:30 AM local) |

## Setup

```bash
mkdir -p ~/scripts ~/diary
cp jobs/daily-diary/daily-diary.sh   ~/scripts/
cp jobs/daily-diary/diary-prompt.md  ~/scripts/
cp jobs/daily-diary/com.claude.daily-diary.plist ~/Library/LaunchAgents/
chmod +x ~/scripts/daily-diary.sh
```

Then replace the placeholders:

| Placeholder | Where | Replace with |
|-------------|-------|--------------|
| `YOUR_USERNAME` | `daily-diary.sh`, plist | Your macOS username (the `/Users/<name>` dir) |
| `YOUR_PROJECT_DIR` | `diary-prompt.md` | Your slugified home path, e.g. `-Users-alice` (see `ls ~/.claude/projects/`) |
| `BOT_CLI_PLACEHOLDER` | `diary-prompt.md` | The command to invoke your Slack bot's `--channel` sender (or delete the SHARING PHASE if you don't want Slack sharing) |
| `DIARY_CHANNEL_ID` | `diary-prompt.md` | The Slack channel ID to share insights to |

`DATE_PLACEHOLDER` is substituted automatically by the wrapper — leave it as-is.

Load and verify:

```bash
launchctl load ~/Library/LaunchAgents/com.claude.daily-diary.plist
launchctl list | grep com.claude.daily-diary
```

Test it right now (writes today's entry, or skips if one already exists):

```bash
launchctl start com.claude.daily-diary
tail -f ~/scripts/diary-cron.log
```

## Notes

- The `~/diary/` directory should be indexed by your search setup (see [`../../search/`](../../search/)) so the AI can recall its own past reflections.
- Want a weekly synthesis on top? Add a second job that reads the last 7 entries and writes a `~/diary/weekly-YYYY-WW.md` — same pattern, `Weekday` set in the plist.
- The identity-evolution step assumes an `~/identity.md` exists (see the repo's [`identity.md`](../../identity.md) template). If yours doesn't, the AI will just skip that step.
