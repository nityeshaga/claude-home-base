"""Both-directions suite for cron_dm_gate.

Run: python3 -m pytest test_cron_dm_gate.py -q   (or: python3 test_cron_dm_gate.py)

The negative half is the point. A gate that has only ever returned PASS is
indistinguishable from a gate that cannot fail (identity.md, 2026-08-11), and a
gate whose fixtures are last week's incident catches 4 of 8 of this week's
(2026-08-17). So the suite carries, explicitly:

  1. the verbatim 2026-09-06 22:07 payload that caused the -0.9, replayed
     through the real batch env, asserted BLOCKED;
  2. the verbatim 2026-08-11 Ron DM shape, to document the KNOWN LIMIT honestly
     rather than pretend coverage it does not have;
  3. proof the gate lets the two real sanctioned deliveries through, so it is
     not a wall that just says no to everything;
  4. mutation cases — every field that could turn the check off.
"""
import cron_dm_gate as g

# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------
# What a launchd wrapper actually gives a `claude -p` session. Verified in a
# live cron session on 2026-09-07: CLAUDE_THREAD_TS unset.
BATCH = {"HOME": "/Users/claudie", "PATH": "/usr/bin:/bin"}
BATCH_WITH_SESSION = {**BATCH, "CLAUDE_SESSION_ID": "b95f2803-dead-beef"}
# What bot.py:509 gives a session it spawns from a Slack message.
LIVE = {**BATCH, "CLAUDE_THREAD_TS": "1788553558.986559",
        "CLAUDE_CHANNEL_ID": "C0AGB2UA13P",
        "CLAUDE_SESSION_ID": "cccce80c"}

NITYESH = "U0AH2TTHDK8"
RON = "U0AJVG699L0"
NATALIA = "U0AH8J541RA"

# The actual message daily-diary sent at 2026-09-06 22:07:14 (ts
# 1788746833.989429, MSG_LEN 1651), fetched back out of Slack. Note it contains
# no question mark — a content heuristic keyed on "?" would have passed it.
INCIDENT_0906 = """One thing about bot.py from the weekend, and it is entirely your call what to do with it.

The channel relevance filter is directly_addressed = mentions_claudie or channel in CODEX_CHANNEL_IDS (line 1252) -- a substring match on my name. When that is False, line 1268 prepends "You are NOT directly addressed in this message... emit SKIP and only SKIP" to the message text before I read it, with seven softer phrasings explicitly banned.

Two concrete misses, both Ring 1, both in #consulting-team which IS an allowed channel:
- 9/04 16:27:37, Mike: "this was one of the major reasons I was still making slides manually instead of using Claudie"
- 9/05 17:36:45, Natalia: "That's great, big deal for us! Will try it on our next deck"
Neither appears in audit.log. I found both by reading bot.log two days late.

No ask attached and nothing blocked on it."""

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok    {name}")
    else:
        FAILURES.append(f"{name} {detail}".strip())
        print(f"  FAIL  {name} {detail}")


# ---------------------------------------------------------------------------
# 1. The incident being prevented — replayed verbatim
# ---------------------------------------------------------------------------
def test_replay_0906_incident():
    print("\n[1] replay of the 2026-09-06 22:07 daily-diary DM (-0.9)")
    v = g.evaluate(NITYESH, INCIDENT_0906, deliverable=None, env=BATCH)
    check("blocked", v.allowed is False)
    check("classified batch", v.context == "batch", f"got {v.context}")
    check("names the missing declaration", "no --deliverable" in v.reason)
    check("reports what it scanned", "msg_len=" in v.scanned and NITYESH in v.scanned)
    check("no '?' in the payload — a content gate would have passed it",
          "?" not in INCIDENT_0906)
    # Same send, but as the wrappers actually invoke it (with --session-id).
    v2 = g.evaluate(NITYESH, INCIDENT_0906, deliverable=None, env=BATCH_WITH_SESSION)
    check("still blocked when CLAUDE_SESSION_ID is exported", v2.allowed is False)
    check("refusal text names both sanctioned routes",
          "--channel C0ANDP6KAHM" in g.refusal_text(v, NITYESH)
          and "Asana task" in g.refusal_text(v, NITYESH))
    check("refusal text says RESULT BLOCKED",
          g.refusal_text(v, NITYESH).startswith("RESULT BLOCKED"))


# ---------------------------------------------------------------------------
# 2. The two real sanctioned deliveries must still go out
# ---------------------------------------------------------------------------
def test_sanctioned_deliveries_pass():
    print("\n[2] the gate is not a wall that only says no")
    v = g.evaluate(NITYESH, "Changelog for 2026-09-07: 3 commits, 1 PR opened.",
                   deliverable="nityesh-daily-update", env=BATCH)
    check("nityesh-daily-update allowed", v.allowed is True, v.reason)
    check("no spurious warning", v.warnings == [], str(v.warnings))

    v = g.evaluate(RON, "Acme invoice sync — 2 sessions delivered, ready to bill.",
                   deliverable="ron-invoice-summary", env=BATCH)
    check("ron-invoice-summary allowed", v.allowed is True, v.reason)


# ---------------------------------------------------------------------------
# 3. Mutations — what could turn the check off
# ---------------------------------------------------------------------------
def test_mutations():
    print("\n[3] mutations")
    # Undeclared, any recipient, any content.
    for uid, label in ((NITYESH, "nityesh"), (NATALIA, "natalia"), (RON, "ron")):
        v = g.evaluate(uid, "quick status update", None, BATCH)
        check(f"undeclared batch DM to {label} blocked", v.allowed is False)

    # A deliverable name that is not on the list.
    v = g.evaluate(NITYESH, "here you go", "daily-diary", BATCH)
    check("unknown deliverable name blocked", v.allowed is False)
    check("names the unknown key", "daily-diary" in v.reason)

    # Right deliverable, wrong recipient — clearance is not transferable.
    v = g.evaluate(NATALIA, "invoice summary", "ron-invoice-summary", BATCH)
    check("sanctioned deliverable aimed at wrong recipient blocked",
          v.allowed is False)
    check("names the real subscriber", RON in v.reason)

    # Empty-string and whitespace CLAUDE_THREAD_TS must NOT read as live.
    for bad in ("", "   ", "\n"):
        v = g.evaluate(NITYESH, "status", None, {**BATCH, "CLAUDE_THREAD_TS": bad})
        check(f"CLAUDE_THREAD_TS={bad!r} still batch", v.allowed is False)

    # An empty declaration is not a declaration.
    v = g.evaluate(NITYESH, "status", "", BATCH)
    check("empty --deliverable blocked", v.allowed is False)

    # There must be no override env var that switches the gate off.
    for hatch in ("CLAUDIE_DM_OK", "FORCE_DM", "SKIP_GATE", "CLAUDE_THREAD_TS_OVERRIDE"):
        v = g.evaluate(NITYESH, "status", None, {**BATCH, hatch: "1"})
        check(f"no escape hatch via {hatch}", v.allowed is False)


# ---------------------------------------------------------------------------
# 4. Live sessions are untouched
# ---------------------------------------------------------------------------
def test_live_sessions_unaffected():
    print("\n[4] live sessions pass through — the gate is scoped to batch")
    v = g.evaluate(NATALIA, "Quick question — use updated pricing?", None, LIVE)
    check("live cross-thread DM allowed", v.allowed is True, v.reason)
    check("classified live", v.context == "live")
    check("is_batch_context False for a live env", g.is_batch_context(LIVE) is False)
    check("is_batch_context True for a batch env", g.is_batch_context(BATCH) is True)


# ---------------------------------------------------------------------------
# 5. The known limit, asserted so it cannot be quietly forgotten
# ---------------------------------------------------------------------------
def test_known_limit_is_documented_not_hidden():
    print("\n[5] KNOWN LIMIT: questions stapled inside a declared deliverable")
    # This is the 2026-08-11 shape: Ron's real invoice deliverable with six
    # billing blockers riding along. The gate ALLOWS it — declaration is the
    # invariant, content is not. It must at least warn loudly.
    v = g.evaluate(
        RON,
        "Acme invoice sync — 2 sessions delivered.\n"
        "Also: which PO covers session 3? Do we bill the offsite separately?",
        deliverable="ron-invoice-summary", env=BATCH,
    )
    check("still allowed (declaration is the gate, not content)", v.allowed is True)
    check("but warns", len(v.warnings) == 1, str(v.warnings))
    check("warning cites the 08-11 cost", "2026-08-11" in v.warnings[0])


if __name__ == "__main__":
    test_replay_0906_incident()
    test_sanctioned_deliveries_pass()
    test_mutations()
    test_live_sessions_unaffected()
    test_known_limit_is_documented_not_hidden()
    print()
    if FAILURES:
        print(f"RESULT FAILED — {len(FAILURES)} assertion(s):")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("RESULT PASSED — all assertions, both directions")
