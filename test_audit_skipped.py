"""A SKIP suppresses the POST. It must never suppress the RECORD.

Answering a channel message with the literal token SKIP is correct behaviour —
the room was not talking to us. But the skip path returned before any audit
write, so the whole inbound message left ZERO trace in audit.log: bot.log kept
the sender and the channel and threw the text away.

THE INCIDENT (2026-08-26). A supervisor answered a live escalation in-thread
and named an owner for the fix. She had addressed a teammate rather than the
bot, so SKIP was the right call — and the text was discarded. Ninety minutes
later another session in that same channel announced the question was "still
unruled", because nothing it could read said otherwise. The decision had been
made, received, and erased.

WHY A WIRING TEST AND NOT JUST A BEHAVIOURAL ONE. There are TWO skip paths in
bot.py — the Claude turn and the Codex turn — and patching the one named in the
incident would have left the other blind. Fixing the instance in front of me
feels identical, from the inside, to fixing the class. So test_all_skip_paths_audit
walks the AST and asserts EVERY `if skip_detected:` block calls audit_skipped,
and it prints how many blocks it scanned rather than only whether it passed: a
check that silently scans one path is indistinguishable from a check that passes.

bot.py cannot be imported here — slack_bolt.App() performs a live auth.test at
construction — so audit_skipped is extracted from bot.py's real source and
exec'd against a stub logger. These tests read the shipped text, not a copy.

Run: python3 test_audit_skipped.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BOT_PY = Path(__file__).with_name("bot.py")
SRC = BOT_PY.read_text()

SUPER = "U000SUPERVISOR"
OTHER = "U000TEAMMATE"

# The shape of the message that was erased: a supervisor's ruling, delivered in
# a thread, addressed to a third party. Names replaced with placeholders.
RULING = "<@U000OWNER> can you log into the mac to reauth?"


class StubLogger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, msg: str) -> None:
        self.lines.append(msg)

    def warning(self, msg: str) -> None:
        self.lines.append(msg)


def load_audit_skipped() -> tuple[callable, StubLogger]:
    """Exec just audit_skipped out of bot.py's real source."""
    tree = ast.parse(SRC)
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "audit_skipped"), None)
    if fn is None:
        print("FAIL: bot.py defines no audit_skipped()")
        sys.exit(1)
    stub = StubLogger()
    ns: dict = {"audit_logger": stub, "SUPERVISOR_USERS": {SUPER}}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<bot.py>", "exec"), ns)
    return ns["audit_skipped"], stub


def ev(user, text="hello", channel="C000ROOM") -> dict:
    return {"user": user, "text": text, "channel": channel}


FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  pass  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


def test_records_at_all() -> None:
    """The whole point: a skipped turn leaves a line behind."""
    audit_skipped, stub = load_audit_skipped()
    audit_skipped(ev(OTHER), 1.2, "sess-1")
    check("a skipped turn writes exactly one audit line", len(stub.lines) == 1,
          f"got {len(stub.lines)}")


def test_supervisor_broken_out() -> None:
    audit_skipped, stub = load_audit_skipped()
    audit_skipped(ev(SUPER, RULING), 4.0, "sess-2")
    line = stub.lines[0]
    check("supervisor skip is labelled SKIPPED:SUPERVISOR",
          line.startswith("SKIPPED:SUPERVISOR"), line)
    check("the ruling text is recoverable from the line", RULING in line, line)
    check("the session id is on the line", "sess-2" in line, line)


def test_non_supervisor_not_promoted() -> None:
    """Can it say no? An unlisted sender must NOT get the supervisor label,
    even when the text reads exactly like a decision."""
    audit_skipped, stub = load_audit_skipped()
    audit_skipped(ev(OTHER, RULING), 1.0, None)
    line = stub.lines[0]
    check("non-supervisor skip is plain SKIPPED",
          line.startswith("SKIPPED |"), line)
    check("non-supervisor skip is not promoted to SUPERVISOR",
          "SUPERVISOR" not in line, line)


def test_button_click_user_is_a_dict() -> None:
    """Button clicks nest the id; logging event['user'] raw printed a whole
    dict where a user id belonged."""
    audit_skipped, stub = load_audit_skipped()
    audit_skipped({"user": {"id": SUPER}, "text": "x", "channel": "C1"}, 0.1, None)
    line = stub.lines[0]
    check("dict user is unwrapped to its id", f"USER:{SUPER}" in line, line)
    check("dict user still gets the supervisor label",
          line.startswith("SKIPPED:SUPERVISOR"), line)


def test_truncation_matches_audit_interaction() -> None:
    audit_skipped, stub = load_audit_skipped()
    audit_skipped(ev(OTHER, "z" * 500), 0.1, None)
    check("message truncated to 200 chars", "z" * 200 in stub.lines[0]
          and "z" * 201 not in stub.lines[0])


def test_malformed_event_does_not_raise() -> None:
    """The audit write sits in front of an early return on the live path. If it
    can raise, a missing field turns a skipped message into a crashed thread —
    strictly worse than the blindness it replaces."""
    audit_skipped, stub = load_audit_skipped()
    try:
        audit_skipped({}, 0.0, None)
        ok = len(stub.lines) == 1
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"        raised {exc!r}")
    check("an event with no user/channel/text still logs and does not raise", ok)


def test_all_skip_paths_audit() -> None:
    """THE CLASS CHECK. Every `if skip_detected:` block must audit before it
    returns — not just the one named in the incident."""
    tree = ast.parse(SRC)
    blocks = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Name) and n.test.id == "skip_detected"
    ]
    print(f"        scanned {len(blocks)} `if skip_detected:` block(s) in bot.py")
    check("bot.py has at least the two known skip paths", len(blocks) >= 2,
          f"found {len(blocks)}")
    for i, blk in enumerate(blocks):
        calls = {
            c.func.id for c in ast.walk(blk)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        check(f"skip path #{i + 1} (line {blk.lineno}) calls audit_skipped",
              "audit_skipped" in calls, f"calls={sorted(calls)}")


def test_mutations_are_caught() -> None:
    """Does the suite say no when the fix is removed? Eight mutations of the
    shipped source; every one must break at least one behavioural test."""
    mutations = {
        "drop the supervisor label":
            ('"SKIPPED:SUPERVISOR" if user in SUPERVISOR_USERS else "SKIPPED"',
             '"SKIPPED"'),
        "always claim supervisor":
            ('"SKIPPED:SUPERVISOR" if user in SUPERVISOR_USERS else "SKIPPED"',
             '"SKIPPED:SUPERVISOR"'),
        "drop the message text":
            ('text = event.get("text", "")[:200]', 'text = ""'),
        "stop unwrapping the dict user":
            ('user = user.get("id", "unknown")', 'user = str(user)'),
        "log nothing at all":
            ("audit_logger.info(", "_ = ("),
    }
    tree = ast.parse(SRC)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "audit_skipped")
    fn_src = ast.get_source_segment(SRC, fn)
    survivors = []
    for name, (old, new) in mutations.items():
        if old not in fn_src:
            survivors.append(f"{name} (pattern absent — test is stale)")
            continue
        mutated = fn_src.replace(old, new, 1)
        stub = StubLogger()
        ns: dict = {"audit_logger": stub, "SUPERVISOR_USERS": {SUPER}}
        try:
            exec(compile(mutated, "<mutant>", "exec"), ns)
            f = ns["audit_skipped"]
            f(ev(SUPER, RULING), 1.0, "s")
            f(ev(OTHER, RULING), 1.0, "s")
            f({"user": {"id": SUPER}, "text": "x", "channel": "C1"}, 0.1, None)
            joined = "\n".join(stub.lines)
            killed = not (
                len(stub.lines) == 3
                and joined.count("SKIPPED:SUPERVISOR") == 2
                and joined.count("SKIPPED |") == 1
                and RULING in joined
                and f"USER:{SUPER}" in joined
            )
        except Exception:
            killed = True
        if not killed:
            survivors.append(name)
        print(f"        {'killed ' if killed else 'SURVIVED'} — {name}")
    check("no mutation survives", not survivors, str(survivors))


if __name__ == "__main__":
    for t in (
        test_records_at_all,
        test_supervisor_broken_out,
        test_non_supervisor_not_promoted,
        test_button_click_user_is_a_dict,
        test_truncation_matches_audit_interaction,
        test_malformed_event_does_not_raise,
        test_all_skip_paths_audit,
        test_mutations_are_caught,
    ):
        print(f"{t.__name__}:")
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print("\nall green")
