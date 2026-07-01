# Jobs

Scheduled background jobs your AI runs on its own — no human in the loop. Each job is a self-contained folder with a wrapper script, a launchd plist, and any prompt files it needs. Copy one in, replace the placeholders, schedule it.

## Available jobs

| Job | Schedule | What it does |
|-----|----------|--------------|
| [`daily-diary/`](daily-diary/) | Nightly 3:30 AM | Reviews the day's conversations and writes an introspective diary entry; optionally evolves `identity.md` and shares an insight to Slack |

(The [`../trust-battery/`](../trust-battery/) judge + reflection jobs follow the same pattern and are documented separately.)

## The pattern

Every job is two files (plus optional prompt/data files):

1. **A wrapper script** (`~/scripts/<job>.sh`) — sets env, timestamps a log, guards against duplicate runs, and calls `claude -p`.
2. **A launchd plist** (`~/Library/LaunchAgents/com.claude.<job>.plist`) — tells macOS when to run the wrapper.

Use **launchd, not cron** — cron can't reach the macOS Keychain, so Claude Code auth fails under it.

## Hard-won rules

These are the mistakes that cost real debugging time. Follow them.

- **Always set `WorkingDirectory` to your home dir in the plist.** Otherwise launchd runs from `/`, and Claude Code creates a split-brain project with its own separate memory and `CLAUDE.md`.
- **Always pass `--dangerously-skip-permissions`** to `claude -p`. There's no TTY to approve prompts; without it the run exits with code 78 and does nothing.
- **Times are LOCAL, not UTC.** Do not convert them. Do not "compensate" for a perceived offset — chasing a nonexistent timezone shift will break every job's schedule. `Weekday`: 0=Sun … 6=Sat.
- **Guard against duplicate runs.** Check whether the output already exists and exit early if so (see `daily-diary.sh`) — launchd can re-fire a missed job on wake.
- **Add a timeout watchdog.** A hung headless run holds resources indefinitely; kill it after a sane limit.
- **Prefer off-peak hours** (avoid 8am–2pm local) for token-heavy jobs.
- **A silently failing scheduled job is the worst kind.** Always write to a log file so you can tell it ran, when, and how it ended.

## Installing a job

Using `daily-diary` as the example:

```bash
# 1. Copy the wrapper and any prompt files into your scripts dir
mkdir -p ~/scripts
cp jobs/daily-diary/daily-diary.sh ~/scripts/
cp jobs/daily-diary/diary-prompt.md ~/scripts/

# 2. Replace YOUR_USERNAME (and any other placeholders — see the job's README)
#    in both the script and the plist, then make the script executable
chmod +x ~/scripts/daily-diary.sh

# 3. Copy the plist and load it
cp jobs/daily-diary/com.claude.daily-diary.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.claude.daily-diary.plist

# 4. Verify it registered
launchctl list | grep com.claude.daily-diary
```

To run it once immediately (great for testing):

```bash
launchctl start com.claude.daily-diary
tail -f ~/scripts/diary-cron.log
```

To remove a job:

```bash
launchctl unload ~/Library/LaunchAgents/com.claude.daily-diary.plist
rm ~/Library/LaunchAgents/com.claude.daily-diary.plist
```

## Adding your own job

Copy `daily-diary/` as a template. Keep the four pieces: the idempotency guard, the timeout watchdog, the log line on start and finish, and a plist with `WorkingDirectory` set. Add a row to the table above and a short README in your job's folder.
