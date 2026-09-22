#!/bin/bash
# Telegram front door: the assistant's Telegram account answers calls and relays audio to bridge.py.
# Setup: copy to ~/scripts/voice-telegram.sh, set BRIDGE_DIR, schedule com.claude.voice-telegram.plist.
# TG_API_ID / TG_API_HASH come from $BRIDGE_DIR/.env.
BRIDGE_DIR="$HOME/claude-home-base/voice-bridge"

cd "$BRIDGE_DIR/telegram" || exit 1
set -a; source "$BRIDGE_DIR/.env"; set +a
mkdir -p ../logs
echo "[$(date '+%F %T')] starting tg_call.py" >> ../logs/telegram.log
exec venv/bin/python tg_call.py >> ../logs/telegram.log 2>&1
