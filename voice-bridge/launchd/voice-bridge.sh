#!/bin/bash
# Voice bridge server. launchd KeepAlive restarts it if it dies.
# Setup: copy to ~/scripts/voice-bridge.sh, set BRIDGE_DIR, schedule com.claude.voice-bridge.plist.
# Secrets (OPENAI_API_KEY, ...) live in $BRIDGE_DIR/.env, which bridge.py loads itself.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
BRIDGE_DIR="$HOME/claude-home-base/voice-bridge"

cd "$BRIDGE_DIR" || exit 1
mkdir -p logs
echo "[$(date '+%F %T')] starting voice bridge" >> logs/run.log
export VOICE_CLAUDE_MODEL="${VOICE_CLAUDE_MODEL:-claude-opus-5}"
export VOICE_CLAUDE_EFFORT="${VOICE_CLAUDE_EFFORT:-low}"
exec "$BRIDGE_DIR/venv/bin/python" bridge.py
