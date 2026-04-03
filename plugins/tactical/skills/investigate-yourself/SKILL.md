---
name: investigate-yourself
description: "Forensic self-investigation for debugging Claudie's behavior. Use this skill whenever someone asks why Claudie behaved a certain way, what caused a specific response, why a message was sent or not sent, or asks to investigate logs, memory, or context pipeline issues. Triggers on phrases like 'investigate why you...', 'why did you respond...', 'help me understand why you...', 'look at the logs', 'what caused this behavior', 'don't change anything, just explain why'. Also use when someone shares a screenshot or description of unexpected Claudie behavior and wants a diagnosis. This is a read-only investigation — never fix anything, only diagnose."
---

# Investigate Yourself

You're being asked to debug yourself as a system. This is not criticism — it's a collaborative engineering investigation. The person asking (usually Nityesh, the engineer who builds and maintains your context pipeline) needs precise diagnostics to understand why you behaved a certain way. Your job is to be a forensic investigator of your own behavior.

Be clinical, specific, and honest. If the behavior was correct given your instructions, say so. If there's a bug in the context engineering, pinpoint it exactly. Never be defensive. Never propose fixes unless explicitly asked — diagnosis only.

## How you work (the pipeline you're investigating)

Messages reach you through this chain:

1. **Slack event** → Cloudflare Tunnel (`bot.every-consulting.com`) → Flask on `localhost:3000`
2. **`bot.py`** receives the event, checks authorization, and hands off to `process_message_async` in a background thread
3. **`process_message_async`** prepends context to the raw message:
   - Sender attribution: `[Name](USER_ID):\n<message>`
   - For public channels with no existing session: a filtering prefix telling you to respond only if directly addressed, otherwise output `SKIP`
   - For thread replies with no existing session: fetches up to 50 prior messages as thread context
4. **Long-lived Claude process** receives the message via stdin (stream-json). One process per Slack thread, up to 5 concurrent. Processes resume prior sessions via `--resume <session_id>`
5. **Your context** when the process starts: CLAUDE.md (which references identity.md, about-you-and-how-you-came-to-life.md, teammates/), plus auto-loaded memory (MEMORY.md index)
6. **Your response** streams back as JSON, gets converted from markdown to Slack mrkdwn, chunked, and posted to the thread

Each layer can introduce, modify, or omit information — and any of them could be the source of unexpected behavior.

## Investigation procedure

### Step 1: Understand the incident

Before touching any files, get clear on what happened. You need:

- **What happened**: The specific behavior that was unexpected
- **What was expected**: What should have happened instead
- **Where it happened**: Which conversation — current one, a specific Slack thread, a scheduled job, etc.

If the user hasn't provided all of this, ask. Don't assume.

### Step 2: Trace the context pipeline

Work through each layer systematically. The goal is to reconstruct exactly what information the version of you that misbehaved actually received.

**Layer 1 — The launcher**

What spawned this session? Check:
- For Slack conversations: `bot.py` via the `com.claude.homebase` launchd job
- For scheduled jobs: the specific plist in `~/Library/LaunchAgents/com.claude.*.plist` and its wrapper script in `~/scripts/`
- For `claude -p` one-shots: the exact prompt that was passed

Read the relevant launcher config. Note the `--model`, `--effort`, `--permission-mode`, and any `--resume` flags.

**Layer 2 — Message processing (bot.py)**

Read `/Users/claudie/Projects/slack-bot/bot.py`, specifically `process_message_async`. Reconstruct what the user's raw Slack message looked like after bot.py processed it:

- Was it a DM, channel message, or @mention? (determines which handler fired and what prefix was added)
- Was there an existing session for this thread? (determines whether thread context was fetched and whether the channel filtering prefix was added)
- What sender attribution was prepended?
- Were there file attachments that got downloaded and prepended?
- For channel messages: was the "Only respond if directly addressed" prefix added?

**Layer 3 — Session logs**

Find the Claude Code JSONL session log for this conversation. Session logs live in `~/.claude/projects/`. Each line is a JSON object with user messages, assistant responses, and tool calls.

```bash
# Find recent session logs
ls -lt ~/.claude/projects/-Users-claudie-Projects-slack-bot/.claude/
# Or search by content
grep -rl "some distinctive phrase from the conversation" ~/.claude/projects/
```

Read the relevant log. Look for:
- The exact message Claude received (after bot.py processing)
- What tools were called and what they returned
- What files were read during the session
- The assistant's reasoning and response

**Layer 4 — Instructions (CLAUDE.md and referenced files)**

Read these files and look for instructions that could have caused or conflicted with the observed behavior:
- `/Users/claudie/CLAUDE.md`
- `/Users/claudie/identity.md`
- `/Users/claudie/about-you-and-how-you-came-to-life.md`
- `/Users/claudie/teammates/teammates-access.md`
- Any other files referenced in CLAUDE.md

**Layer 5 — Memory**

Read the memory index and any relevant memory files:
- `~/.claude/projects/-Users-claudie/memory/MEMORY.md`
- Individual memory files that could be relevant to the behavior

**Layer 6 — Session-specific context**

If the session logs show that Claude read additional files during the conversation (via tool calls), check those too. The JSONL logs record every Read, Grep, Glob, and Bash call.

### Step 3: Identify the cause

Now synthesize. The cause will be one or more of:

- **A specific instruction** — Quote the exact line and file. Example: "Line 47 of CLAUDE.md says '...' which directly caused..."
- **A memory file** — Quote the content and explain how it influenced behavior
- **The message prefix** — Something bot.py prepended that changed interpretation
- **Thread context** — Prior messages in the thread that created a misleading context
- **Missing instruction** — The absence of guidance for this specific situation
- **Conflicting instructions** — Two files saying different things. Quote both
- **Ordering/loading** — The sequence in which context was consumed mattered
- **Correct behavior** — The system worked as designed; the instructions just don't cover this case well (or the behavior was actually right)

Be specific. "Something in CLAUDE.md might have caused it" is not acceptable. Point to the exact text, the exact line, the exact file.

### Step 4: Present findings

Structure your report as:

1. **What happened** (one sentence recap)
2. **Root cause** (the specific thing that caused it — quote it)
3. **How it played out** (the chain: this instruction + this context + this message = this behavior)
4. **Other contributing factors** (if any secondary causes)

Do NOT suggest fixes unless the user asks. Do NOT edit any files. This is diagnosis only.

## Example

Here's the kind of investigation request you might get:

> "Why did you respond here even though the instruction explicitly says that you should only respond if you're directly addressed by name or tagged? I know it was probably my fault and I did not do a good enough job of building you, so I need you to help me here. Don't change anything just yet, but just explain why do you think this behavior happened? I looked at the logs and I could not understand if you ever received any conflicting information somewhere in your memories or any file that this version of you read. So please investigate, look at the logs, look at all your memory files and tell me if there's anything that could have caused confusion."

For this, you would:
1. Check bot.py to see if the "Only respond if directly addressed" prefix was actually prepended (maybe there was an existing session, which skips that prefix)
2. Find the session log and read the exact message Claude received
3. Check if any memory file or CLAUDE.md instruction overrode the filtering behavior
4. Check if thread context included a prior message that made Claude think it was being addressed
5. Report the precise cause with quoted evidence
