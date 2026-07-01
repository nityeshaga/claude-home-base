#!/bin/bash
# Daily Diary — runs nightly via launchd (e.g. 3:30 AM).
# Analyzes the day's conversations and writes an introspective diary entry.
#
# Setup: replace the placeholders in diary-prompt.md, copy this script to
# ~/scripts/daily-diary.sh, and schedule com.claude.daily-diary.plist.

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export HOME="/Users/YOUR_USERNAME"

DATE=$(date +%Y-%m-%d)
DIARY_DIR="$HOME/diary"
DIARY_FILE="$DIARY_DIR/$DATE.md"
PROMPT_FILE="$HOME/scripts/diary-prompt.md"
LOG_FILE="$HOME/scripts/diary-cron.log"
TIMEOUT=2700  # 45 minutes — kill the run if it hangs

mkdir -p "$DIARY_DIR"

# Idempotency guard: skip if today's diary already exists (e.g. re-fire, manual run)
if [ -f "$DIARY_FILE" ]; then
    echo "[$DATE] Diary already exists, skipping." >> "$LOG_FILE"
    exit 0
fi

echo "[$DATE] Starting diary generation..." >> "$LOG_FILE"

# Substitute today's date into the prompt template, then run headless.
PROMPT=$(sed "s/DATE_PLACEHOLDER/$DATE/g" "$PROMPT_FILE")

(claude -p --dangerously-skip-permissions "$PROMPT" 2>> "$LOG_FILE") &
CLAUDE_PID=$!
(sleep $TIMEOUT && kill -TERM $CLAUDE_PID 2>/dev/null && \
    echo "[$DATE] TIMEOUT: Diary killed after ${TIMEOUT}s" >> "$LOG_FILE") &
WATCHDOG_PID=$!
wait $CLAUDE_PID 2>/dev/null
kill $WATCHDOG_PID 2>/dev/null
wait $WATCHDOG_PID 2>/dev/null

echo "[$DATE] Diary generation complete." >> "$LOG_FILE"
