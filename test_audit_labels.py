"""The audit log must say what actually happened.

Two defects, both in what audit.log CLAIMS about the room rather than in the
bot's behaviour — which was correct throughout:

  1. MISLABELLING. AUTHORIZED_USERS holds only the three Ring 1 names, so every
     Ring 2 teammate got stamped "UNAUTHORIZED" while being served normally. On
     2026-08-16, 38 of the day's 60 audit lines read as rejections when nothing
     had been rejected.
  2. BLINDNESS. The channel-prefix early return fired before any audit write,
     and log_unauthorized never fired for a listed user — so the one class of
     message leaving ZERO trace was an AUTHORIZED supervisor posting in a
     non-allowed channel. Mike's 08-16 17:02 post left one bot.log line and
     nothing in audit.log; Dan Shipper's, three minutes later, left two.

The battery judge reads this file nightly and has reasoned from both defects, so
"audit.log was empty" / "the log said unauthorized" were claims about the
logging, not about the room.

bot.py cannot be imported here — slack_bolt.App() performs a live auth.test at
construction — so the three logging helpers are extracted from bot.py's real
source and exec'd against a stub logger. That means these tests read the shipped
text, not a copy of it.

Run: python3 test_audit_labels.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BOT_PY = Path(__file__).with_name("bot.py")
SRC = BOT_PY.read_text()

WANT = ("_audit_user_id", "log_unlisted_user", "log_ignored_channel")


class StubLogger:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def warning(self, msg: str) -> None:
        self.lines.append(("WARNING", msg))

    def info(self, msg: str) -> None:
        self.lines.append(("INFO", msg))


def load_helpers() -> tuple[dict, StubLogger]:
    """Exec just the logging helpers out of bot.py's real source."""
    tree = ast.parse(SRC)
    wanted = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name in WANT]
    missing = set(WANT) - {n.name for n in wanted}
    if missing:
        print(f"FAIL: bot.py is missing {sorted(missing)}")
        sys.exit(1)
    stub = StubLogger()
    ns: dict = {"audit_logger": stub}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "<bot-helpers>", "exec"), ns)
    return ns, stub


def main() -> int:
    ok = True
    ns, stub = load_helpers()

    # --- 1. the retired label is gone from the whole file ----------------
    if "UNAUTHORIZED |" in SRC:
        print("FAIL: the bare 'UNAUTHORIZED |' label still appears in bot.py")
        ok = False
    if "log_unauthorized" in SRC:
        print("FAIL: log_unauthorized still referenced — call sites not migrated")
        ok = False

    # --- 2. a served channel message is NOT logged as refused -----------
    served = {"user": "U0AJR6U4VKJ", "channel": "C0ANDP6KAHM", "text": "hey claudie"}
    ns["log_unlisted_user"](served, "SERVED")
    lvl, line = stub.lines[-1]
    if "SERVED" not in line:
        print(f"FAIL: served message not labelled SERVED: {line}")
        ok = False
    if "REFUSED" in line:
        print(f"FAIL: served message labelled REFUSED: {line}")
        ok = False
    if "U0AJR6U4VKJ" not in line:
        print(f"FAIL: user id missing from audit line: {line}")
        ok = False

    # --- 3. a refused DM is still unambiguously refused -----------------
    ns["log_unlisted_user"]({"user": "U9NOBODY", "channel": "D123", "text": "hi"},
                            "REFUSED")
    lvl, line = stub.lines[-1]
    if "REFUSED" not in line or lvl != "WARNING":
        print(f"FAIL: refused DM should be a WARNING labelled REFUSED: {lvl} {line}")
        ok = False

    # --- 4. the previously-invisible case now leaves a line -------------
    # Mike (Ring 1, listed) in #every-one: the exact message that produced
    # zero audit lines on 2026-08-16.
    before = len(stub.lines)
    ns["log_ignored_channel"](
        {"user": "U0AH9KM0PE1", "channel": "C0AH7N6HJ0Y",
         "text": "https://x.com/i/status/2089088356676440483"},
        "MESSAGE",
    )
    if len(stub.lines) != before + 1:
        print("FAIL: ignored-channel message still leaves no audit line")
        ok = False
    else:
        lvl, line = stub.lines[-1]
        for frag in ("IGNORED_CHANNEL", "U0AH9KM0PE1", "C0AH7N6HJ0Y"):
            if frag not in line:
                print(f"FAIL: ignored-channel line missing {frag!r}: {line}")
                ok = False
        if lvl != "INFO":
            print(f"FAIL: ignoring is correct behaviour, should be INFO not {lvl}")
            ok = False

    # --- 5. button-click payloads log a plain user id -------------------
    # body["user"] is a dict on block_actions; the old code logged USER:{'id':…}
    if ns["_audit_user_id"]({"user": {"id": "U0AH2TTHDK8", "name": "n"}}) != "U0AH2TTHDK8":
        print("FAIL: nested block_actions user id not unwrapped")
        ok = False
    if ns["_audit_user_id"]({"user": "U0AH8J541RA"}) != "U0AH8J541RA":
        print("FAIL: plain string user id broken")
        ok = False
    if ns["_audit_user_id"]({}) != "unknown":
        print("FAIL: missing user should degrade to 'unknown'")
        ok = False

    # --- 6. call sites carry the right outcomes -------------------------
    expectations = [
        ('log_unlisted_user(event, "REFUSED")', 2, "DM refusal in message + mention"),
        ('log_unlisted_user(event, "SERVED")', 2, "channel fall-through"),
        ('log_unlisted_user(body, "REFUSED")', 1, "block_actions"),
        ('log_ignored_channel(event, "MESSAGE")', 1, "message ignore path"),
        ('log_ignored_channel(event, "MENTION")', 1, "mention ignore path"),
    ]
    for frag, want, what in expectations:
        got = SRC.count(frag)
        if got != want:
            print(f"FAIL: {what}: expected {want}x {frag!r}, found {got}")
            ok = False

    print(f"{len(stub.lines)} audit lines exercised across 4 outcomes.")
    print("ALL PASS" if ok else "TESTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
