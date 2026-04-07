---
name: interview-me
description: Start a timed discovery interview with the user. Use this skill when the user wants to be interviewed, wants you to ask them questions to learn about them or what they're working on, says "interview me", "ask me questions", "do a discovery call", or wants a structured Q&A session. Default duration is 5 minutes.
---

# Interview Me

Start a timer in the background and interview the user. Do a little discovery call so you can learn more about them and what they're trying to do.

$ARGUMENTS

(default: 5 mins)

## Setup

First, start a background timer and store the process ID:

```bash
sleep 300 & echo $! > /tmp/discovery-timer-pid && echo "Timer started"
```

This starts a 5-minute timer. Adjust 300 (seconds) if the user requests a different duration. You MUST start this as a background task so the interview can proceed.

## After Every User Response

Check remaining time by running:

```bash
pid=$(cat /tmp/discovery-timer-pid 2>/dev/null) && if ps -p $pid > /dev/null 2>&1; then start_time=$(ps -o lstart= -p $pid | xargs -I {} date -j -f "%c" "{}" "+%s" 2>/dev/null) && now=$(date "+%s") && elapsed=$((now - start_time)) && remaining=$((300 - elapsed)) && echo "~$remaining seconds remaining (~$((remaining/60)) min)"; else echo "Timer complete"; fi
```

Don't overwhelm with multiple questions. One question, wait for response, check timer, next question.

## When Time Is Up

Summarize what you learned:
1. **Who they are** — role, context, what they care about
2. **What they're trying to do** — the goal or problem they described
3. **Key insights** — the 2-3 most important things that came out
4. **Open questions** — what still needs to be figured out
