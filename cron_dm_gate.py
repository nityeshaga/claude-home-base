"""Stop a batch/cron session from DMing a human anything it did not declare.

Why this exists
---------------
2026-09-06 22:07:14. `daily-diary` — a job whose prompt authorizes research, a
diary entry, an identity reflection and last-night.md, and no outbound Slack at
all — DMed Nityesh a 1,651-character bug report about bot.py. Sunday night,
SESSION:none, no ask attached. It cost -0.9 and put his battery down -0.6 on a
day with no interaction in it.

It is the third instance of one class:
  * 2026-06-09  flat -10 across EVERY battery. "Claudie's asks in DMs and public
                channels have been too noisy and the team has stopped taking
                them seriously."
  * 2026-07-01  a 4am client-project DM to a teammate, -0.7.
  * 2026-08-11  six billing blockers stapled to Ron's invoice DM, -1.0. The rule
                was sharpened the next day in response.
  * 2026-09-06  this one, AFTER the sharpening, with no prompt instructing it.

Why the existing defense could not see it
-----------------------------------------
`job-health-monitor.py` already greps every live wrapper in ~/scripts for
`bot.py --send` and flags anything outside its SANCTIONED_DM set. That check is
pointed one layer off the target: it reads the *static text of wrapper scripts*,
and the 09-06 send was a runtime decision made by the model inside a session,
via the Bash tool. No wrapper contained the string. The check was also parked
and not running. So a policy with a grep behind it was, in practice, prose.

The instrument has to sit at the layer the act passes through, and that layer is
`bot.py --send`. Every proactive DM — from a wrapper, from a model's Bash call,
from a human at the keyboard — goes through this one function.

Design notes
------------
* THE GATE IS DECLARATION, NOT CONTENT. A batch caller must name the subscribed
  deliverable it is sending; an undeclared or unrecognized name is refused. No
  judgment to exercise, which per identity.md is the shape that should be a gate
  rather than a suggestion. Content heuristics were explicitly considered and
  rejected as the gate: the rule of thumb on file is "if the message has a
  question mark in it, it is not a deliverable," and the 09-06 payload contains
  no question mark. A content gate would have passed it. The question-mark tell
  survives here as a loud WARN on a declared send, never as the block.
* FAIL CLOSED, AND ON THE ENVIRONMENT, NOT ON A FLAG THE CALLER CHOOSES. Batch
  context is inferred from the absence of CLAUDE_THREAD_TS, which bot.py sets on
  every session it spawns from Slack (bot.py:509) and which no launchd wrapper
  ever sets. A caller cannot opt out of being batch.
* NO OVERRIDE ENV VAR. The 2026-08-14 lesson: a gap in an allowlist is findable
  by auditing the allowlist, a disabled check is not, because the list is fine
  and nothing ever ran. So there is no CLAUDIE_DM_OK escape hatch. If a live
  human needs a send the gate refuses, the answer is `--channel` or a declared
  deliverable, both of which leave a record.
* A DISTINCT EXIT CODE. `xargs -a` cost a day in 2026-08-12 because a crashed
  wrapper exits 1 and so does a refusal. BLOCKED exits 3 and prints
  "RESULT BLOCKED" plus the recipient and the reason, so a refusal and a corpse
  are never confused from outside.

Known limit, stated rather than papered over: this gate stops an UNDECLARED DM.
It does not stop questions stapled inside a DECLARED deliverable — the 08-11
failure. That one stays governed by the wrapper prompts (my-tasks-complete STEP
C strips blockers out of Ron's invoice DM) and is surfaced here only as a WARN.
"""
import os

# deliverable name -> (recipient user id, why this DM is subscribed output)
#
# Mirrors SANCTIONED_DM in ~/scripts/job-health-monitor.py. Keyed on the
# recipient as well as the name so a sanctioned job cannot lend its clearance
# to a send aimed at somebody else.
SANCTIONED_DELIVERABLES: dict[str, tuple[str, str]] = {
    "nityesh-daily-update": (
        "U0AH2TTHDK8",
        "Nityesh's daily changelog digest, requested by name 2026-08-11",
    ),
    "ron-invoice-summary": (
        "U0AJVG699L0",
        "Ron's invoice summaries — he is not an Asana user, DM is the only "
        "surface that reaches him (my-tasks-complete STEP C)",
    ),
}

# Where a batch job's human-needed item is supposed to go instead.
ADMIN_CHANNEL = "C0ANDP6KAHM"  # #claudie-admins


class Verdict:
    """Outcome of the gate. `scanned` exists so the instrument reports what it
    looked at, not only what it returned — a verdict with no corpus behind it
    is indistinguishable from a check that did nothing (2026-08-12)."""

    def __init__(
        self,
        allowed: bool,
        context: str,
        reason: str,
        scanned: str,
        warnings: list[str] | None = None,
    ):
        self.allowed = allowed
        self.context = context      # "live" | "batch"
        self.reason = reason
        self.scanned = scanned
        self.warnings = warnings or []

    def __repr__(self) -> str:
        state = "ALLOW" if self.allowed else "BLOCK"
        return f"<Verdict {state} context={self.context} reason={self.reason!r}>"


def is_batch_context(env: dict | None = None) -> bool:
    """True when no human is waiting in a Slack thread for this process.

    bot.py:509 sets CLAUDE_THREAD_TS on every session it spawns from a Slack
    message, and thread_ts there is always non-empty (`event["thread_ts"] or
    event["ts"]`). Every launchd wrapper in ~/scripts exports PATH, HOME and
    sometimes CLAUDE_SESSION_ID — none of them sets CLAUDE_THREAD_TS. So an
    empty CLAUDE_THREAD_TS means nobody is on the other end of this send.
    """
    e = os.environ if env is None else env
    return not (e.get("CLAUDE_THREAD_TS") or "").strip()


def evaluate(
    user_id: str,
    message: str,
    deliverable: str | None = None,
    env: dict | None = None,
) -> Verdict:
    """Decide whether this proactive DM may go out."""
    e = os.environ if env is None else env
    thread = (e.get("CLAUDE_THREAD_TS") or "").strip()
    session = (e.get("CLAUDE_SESSION_ID") or "").strip()
    scanned = (
        f"recipient={user_id} msg_len={len(message)} "
        f"deliverable={deliverable or 'none'} "
        f"CLAUDE_THREAD_TS={thread or 'unset'} "
        f"CLAUDE_SESSION_ID={session or 'unset'}"
    )

    if not is_batch_context(env):
        # A live Slack session. The human is in the thread; ordinary judgment
        # and the three-legged proactive-contact bar apply, and they are not
        # this module's business.
        return Verdict(True, "live", "live session (CLAUDE_THREAD_TS set)", scanned)

    if not deliverable:
        return Verdict(
            False,
            "batch",
            "batch session with no --deliverable declared. A cron may DM a "
            "human a deliverable they subscribed to; it may never DM a "
            "question, blocker, status line or failure notice.",
            scanned,
        )

    entry = SANCTIONED_DELIVERABLES.get(deliverable)
    if entry is None:
        return Verdict(
            False,
            "batch",
            f"deliverable {deliverable!r} is not in SANCTIONED_DELIVERABLES "
            f"(known: {', '.join(sorted(SANCTIONED_DELIVERABLES))})",
            scanned,
        )

    expected_recipient, why = entry
    if user_id != expected_recipient:
        return Verdict(
            False,
            "batch",
            f"deliverable {deliverable!r} is subscribed by "
            f"{expected_recipient}, not {user_id}. A sanctioned job cannot "
            f"lend its clearance to a different recipient.",
            scanned,
        )

    warnings = []
    if "?" in message:
        # Not a block. The tell on file — "if the message has a question mark
        # in it, it is not a deliverable" — is a heuristic about content, and a
        # check that cries wolf on Ron's invoices is how a real one gets waved
        # through later. It is recorded loudly and the send proceeds.
        warnings.append(
            "declared deliverable contains a '?' — a deliverable with "
            "questions stapled to it is a question (cost -1.0 on 2026-08-11). "
            "Verify the ask belongs in the channel post instead."
        )

    return Verdict(True, "batch", f"sanctioned deliverable: {why}", scanned, warnings)


def refusal_text(verdict: Verdict, user_id: str) -> str:
    """What the blocked caller is told. Names the two sanctioned routes, so the
    refusal ends in a next action rather than in a wall."""
    return (
        "RESULT BLOCKED\n"
        f"cron_dm_gate refused a proactive DM to {user_id}.\n"
        f"SCANNED  {verdict.scanned}\n"
        f"REASON   {verdict.reason}\n"
        "ROUTE INSTEAD:\n"
        f"  * work-hours channel post, @-tagging the owner:\n"
        f"      bot.py --channel {ADMIN_CHANNEL} \"<@USER> <the ask>\" "
        f"--session-id $CLAUDE_SESSION_ID\n"
        "  * or a tracked Asana task with a due date "
        "(see the report-to-nityesh skill for infrastructure findings).\n"
        "If this really is a subscribed deliverable, add it to "
        "SANCTIONED_DELIVERABLES in cron_dm_gate.py and pass "
        "--deliverable <name>."
    )
