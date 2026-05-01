# Trust Battery

A system for measuring and improving the trust relationship between your AI employee and each team member. Inspired by [Tobi Lütke's trust battery concept](https://fs.blog/tobi-lutke/) — every relationship starts at 50% charge, and every interaction either charges or drains it.

## How it works

Two scheduled jobs run back-to-back each night:

1. **Battery Judge** (3:00 AM) — An independent evaluator agent that reviews the day's interactions and assigns a trust charge delta to each team member. It reads conversation logs, Slack history, scheduled job outcomes, and memory files to find specific evidence of good work and friction.

2. **Self-Reflection** (4:00 AM) — The AI employee reads the judge's verdict, identifies patterns, and takes corrective action. This is where behavioral change actually happens — fixing prompts, updating memory files, adjusting workflows, or reaching out to team members.

## Autonomy tiers

The trust battery charge maps to how much autonomy the AI gets with each person:

| Charge | Tier | Behavior |
|--------|------|----------|
| 0–25% | Propose and Wait | Draft actions, ask before executing |
| 25–50% | Routine Execution | Handle routine tasks, ask on judgment calls |
| 50–75% | Judgment Calls | Make non-trivial decisions, report afterward |
| 75–100% | Full Autonomy | Act independently, brief on outcomes |

The bot injects current battery state into every Claude session, so the AI adjusts its behavior based on earned trust with whoever it's talking to.

## Setup

### 1. Create battery files

Create a JSON file for each team member in a directory (e.g., `~/trust-battery/`):

```bash
mkdir -p ~/trust-battery/reflections
```

See `example.json` for the schema. Initialize each team member at 50%:

```json
{
  "team_member": "Alice",
  "slack_id": "U0XXXXXXXXX",
  "current_charge": 50.0,
  "last_updated": "2025-01-01",
  "last_interaction_date": null,
  "history": []
}
```

### 2. Set up the judge job

Create a shell wrapper script (`~/scripts/trust-battery.sh`):

```bash
#!/bin/bash
set -euo pipefail
LOG=~/scripts/trust-battery.log

echo "$(date '+%Y-%m-%d %H:%M:%S') | START trust-battery" >> "$LOG"

claude -p "$(cat ~/trust-battery/battery-judge-prompt.md)" \
  --model claude-opus-4-6 \
  --permission-mode dontAsk \
  2>&1 | tail -20 >> "$LOG"

echo "$(date '+%Y-%m-%d %H:%M:%S') | DONE trust-battery" >> "$LOG"
```

### 3. Set up the reflection job

Create another wrapper (`~/scripts/trust-battery-reflect.sh`):

```bash
#!/bin/bash
set -euo pipefail
LOG=~/scripts/trust-battery-reflect.log

# Skip weekends
DOW=$(date +%u)
if [ "$DOW" -ge 6 ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') | SKIP weekend" >> "$LOG"
  exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') | START trust-battery-reflect" >> "$LOG"

claude -p "$(cat ~/trust-battery/self-reflection-prompt.md)" \
  --model claude-opus-4-6 \
  --dangerously-skip-permissions \
  2>&1 | tail -20 >> "$LOG"

echo "$(date '+%Y-%m-%d %H:%M:%S') | DONE trust-battery-reflect" >> "$LOG"
```

### 4. Schedule with launchd

Create plist files in `~/Library/LaunchAgents/`:

**Judge** (`com.claude.trust-battery.plist`) — runs at 3:00 AM:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.trust-battery</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/YOUR_USERNAME/scripts/trust-battery.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
```

**Reflection** (`com.claude.trust-battery-reflect.plist`) — runs at 4:00 AM:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.trust-battery-reflect</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/YOUR_USERNAME/scripts/trust-battery-reflect.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>4</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
```

Load them:
```bash
launchctl load ~/Library/LaunchAgents/com.claude.trust-battery.plist
launchctl load ~/Library/LaunchAgents/com.claude.trust-battery-reflect.plist
```

### 5. Enable in bot

Set `TRUST_BATTERY_DIR` in your `.env`:

```
TRUST_BATTERY_DIR=/Users/YOUR_USERNAME/trust-battery
```

The bot will now inject trust battery context into every Claude session.

## Files

| File | Purpose |
|------|---------|
| `battery-judge-prompt.md` | Instructions for the nightly judge agent |
| `self-reflection-prompt.md` | Instructions for the nightly reflection agent |
| `example.json` | Schema example for per-user battery files |
| `reflections/` | Daily reflection logs (created by the reflection job) |

## Why this works

The trust battery creates a feedback loop that most AI setups lack. Without it, an AI employee repeats the same mistakes because there's no durable signal about what's working and what isn't. The judge provides the signal; the reflection provides the correction.

The autonomy tiers make the feedback actionable — a low battery doesn't just mean "do better," it means "ask before acting." A high battery means earned independence. This mirrors how human trust works: you don't give someone full autonomy on day one, you let them earn it.
