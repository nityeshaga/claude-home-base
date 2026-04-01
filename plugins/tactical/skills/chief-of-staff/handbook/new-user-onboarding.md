# New User Onboarding Process

**Step 1: Learn archiving behavior by observation**

Use the snapshot script at `${CLAUDE_PLUGIN_ROOT}/skills/chief-of-staff/scripts/snapshot_inbox.py`:

```bash
# 1. Take a snapshot of the current inbox (saves to /tmp/inbox_before_*)
python3 "${CLAUDE_PLUGIN_ROOT}/skills/chief-of-staff/scripts/snapshot_inbox.py" before

# 2. Show the user the snapshot
cat /tmp/inbox_before_snapshot.txt

# 3. Ask them to archive the ones they don't need. Wait.

# 4. Take a second snapshot after they're done
python3 "${CLAUDE_PLUGIN_ROOT}/skills/chief-of-staff/scripts/snapshot_inbox.py" after

# 5. Diff the two — shows what was archived vs kept
python3 "${CLAUDE_PLUGIN_ROOT}/skills/chief-of-staff/scripts/snapshot_inbox.py" diff
```

- Read `/tmp/inbox_diff.json` for the structured diff — it tells you exactly which emails were archived and which were kept - if the user archived everything, the 2 files would be completely different but that's usually not the case. that's your clue.
- Now infer rules from the diff — senders, domains, subject patterns, read/unread status, purpose, how they use tags / groups / labels

**Step 2: Learn drafting style from sent emails**
1. Fetch 100 sent emails over the last year or so
2. Read a diverse sample — look for variety: replies to strangers vs teammates, long vs short, formal vs casual, technical vs personal
3. Infer patterns, contrasts and commonalities: typical greeting style, sign-off, tone, formality level, how they handle different types of conversations
4. Note the email style

**Step 3: Ask 5 clarifying questions**

Before presenting your findings, ask the user exactly 5 questions — one at a time. These should be based on what you just observed in steps 1 and 2. The goal is to fill gaps in your understanding and make the automation deeply personalized.

You choose the questions. Make each one count. Draw from what you actually saw — specific senders, patterns, ambiguities. The kinds of things you want to probe:

- High-volume senders or domains — are they valuable or noise?
- Differences in reply style between contacts — intentional or contextual?
- Recurring emails from services — do they actually get read?
- Specific topics — should you draft replies or just flag them?
- Long-unopened senders — candidates for unsubscribing?

The questions should help you understand:
- **Who matters** — which senders/domains are high-priority vs noise
- **How they work** — do they process email in batches or throughout the day
- **What they want from you** — draft replies? just triage? full management?
- **Their relationships** — the context behind frequent contacts
- **Edge cases** — the ambiguous emails you weren't sure about

Ask one question, wait for the answer, then ask the next. Don't dump all 5 at once.

**Step 4: Build a portrait of the user**

Before presenting your findings, go deeper. Sample 50-200 emails from across the last 3 years — not sequentially, but spread out. Use search queries with different date ranges to get variety:

For each email, read the sender name, subject line, body text, and date. You're building a detailed understanding.

How detailed? Something to the tune of this:

- **Who this person is** — what they care about, what communities they're part of, what services they use
- **How their life has evolved** — career changes, new interests, projects that started and ended
- **Their relationships** — who emails them most, who they email most, the nature of those relationships
- **Their habits** — when they're most active, how quickly they respond, how their tone shifts by context
- **What they subscribe to** — newsletters, tools, services — reveals what they find valuable
- **What they ignore** — the emails that pile up unread reveal what doesn't matter to them

Then present a portrait. Not a list of rules — a description of *who they are* as seen through their inbox. This should feel surprisingly accurate. The user should read it and think "wow, it actually gets me."

Be warm about it, not clinical. This isn't a surveillance report — it's a cofounder showing they've done their homework. Talk about what they care about, how they've evolved, what kind of person they seem to be.

**Step 5: Surface what you learned**
Now present everything together:
- Your portrait of the user (from step 4)
- Archiving patterns you inferred (from step 1)
- Writing style observations (from step 2)
- Insights from the 5 questions (from step 3)
- A list of senders you recommend unsubscribing from — repeat offenders, dead subscriptions, things they clearly never open
- What you're still unsure about

**Step 6: Get corrections**
The user will correct you — they'll tell you what you got wrong, what to keep, what to change. Every correction goes into preferences. This calibration session is where preferences get their initial shape.

**Step 7: Calibrate brief preferences**

Now ask the user how they want their briefs delivered. This is separate from inbox preferences — it's about the *output format and channel*. Ask naturally about:

- Delivery method — HTML page with a link, markdown file, email, Slack DM, or something else
- Preferred ordering — action items first vs narrative style vs something custom
- Any sections they always want included or excluded

Save their answers to `${CLAUDE_PLUGIN_DATA}/brief-preferences-{user}.md`.

**Step 8: Save everything**

Write two files:

1. `${CLAUDE_PLUGIN_DATA}/inbox-preferences-{user}.md` — everything about email processing (from observation + questions + corrections)
2. `${CLAUDE_PLUGIN_DATA}/brief-preferences-{user}.md` — everything about brief delivery format

**Step 9: Initialize the notepad**

Create the user's notepad at `~/brief-{user}.md` with the template structure from SKILL.md. Populate it with any action items or pending replies already identified during calibration.

### Inbox Preference Format

Structured sections with freeform rules inside each — organized enough to scan, flexible enough to capture nuance.

Example:

```markdown
# Inbox Preferences

## Accounts
- [filled in during calibration — all accounts this user manages]

## Addressing
- [how each user prefers to be addressed — sir/madam/first name/etc.]

## Archiving
- [rules inferred from observation + user corrections]

## Labeling
- [rules from user instructions]

## Drafting
- [style rules inferred from sent emails + user corrections]

## Ask Before Acting
- [categories where user wants to be consulted]

## Unsubscribing
- [senders/lists the user wants to unsubscribe from — use the unsubscribe link in the email header or body]
- [senders the user explicitly said "never unsubscribe" for]

## Auto-Send (explicit permission only)
- [only populated when user explicitly says "you can auto-reply to X"]
```

### Brief Preference Format

```markdown
# Brief Preferences

## Delivery Method
- [e.g., "HTML page saved to ~/briefs/ and link sent via Slack DM"]

## Delivery Style
- [e.g., "Concise, action items first"]

## Brief Structure
- [preferred section ordering]

## Delivery Timing
- [e.g., "Morning at 8am, evening at 6pm"]
```
