# The Notepad

The notepad (`~/brief-{user}.md`) is the persistent working document per user — always current, accumulates between runs. The delivered brief is a formatted snapshot of it; the notepad is the truth about *what is tracked*, but never the truth about *whether something is still open* — that truth lives at the item's source, and every item records how to check it (see Item format).

## Structure

Loose structure with guided sections. Add, remove, or rename sections per the user's needs, but these are always present:

```markdown
# Brief — {User}

## Action Items
Items the user needs to act on (subcategorize: assistant-handleable vs needs-human).

## Pending Replies
Messages awaiting a response from the user.

## To Brief
One-shot content gathered since last delivery — delivered once, then cleared.

## Notes
Freeform: context, observations, "Resolved this run" one-liners.
```

## Item format — every carried item records its own done-check

Any item that carries between briefs (Action Items, Pending Replies, Loose Ends) MUST be written with two metadata lines at capture time, while context is fresh:

```markdown
- [ ] Samyr (hi@samyr.co) — answer his member-edit question
  verify: gws gmail thread 19e6b55a2a7d9a33 — done when last message is from {user} OR thread no longer in INBOX
  added: 2026-06-08

- [ ] PR #933 (match-history import) — needs review
  verify: gh pr view 933 --repo nityeshaga/curated_connections_2 — done when merged/closed, or reviewed by {user}
  added: 2026-06-08
```

The `verify:` line is a one-line predicate any future session or agent can execute mechanically: **where to look** (a thread id, a PR number, a URL, a Slack channel) and **what state means done**. Writing it at capture time is the whole point — the capturing session knows the source; a verifying session a week later should not have to re-derive it.

`To Brief` items are one-shot and need no `verify:` line.

## Resolution conventions

What counts as "handled" is per-person and lives in `${CLAUDE_PLUGIN_DATA}/brief-preferences-{user}.md` under a "Resolution conventions" section. Defaults when a user has no explicit rule:

- **Email**: the thread is no longer in INBOX = handled, **regardless of whether a reply exists**. Check the thread/message state by id; do not infer from sent-folder searches.
- **PRs/issues**: merged or closed = done. "Needs review" is resolved by any review activity from the user.
- **A check that cannot run** (auth failure, API down) = *unverifiable*, never *open* and never *resolved*. Unverifiable items carry forward with a dated "(unverified)" label; after 2+ consecutive unverifiable runs, ask the user to confirm-or-drop instead of re-surfacing.

## Lifecycle

- **Between runs**: always writable. When the user says "add X to my todos" or another skill queues something — read, append to the right section **with `verify:` and `added:` lines**, write back.
- **During a triage run**: the workflow parses items, verifies each against its `verify:` predicate, and only survivors reach the composed brief. Resolved items move to Notes → "Resolved this run" (one line + evidence) and the activity log, so they are never re-added.
- **After delivery**: keep everything unresolved (with metadata lines intact); clear To Brief and resolved one-liners older than one run.
- **Never re-add dropped items**: before adding any item, check Notes and the activity log for a prior resolution/drop of the same item.
- **The notepad is sacred**: read before writing, preserve open items, never overwrite carelessly.
