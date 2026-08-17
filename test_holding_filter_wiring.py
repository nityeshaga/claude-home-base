"""Wiring test for the holding filter in bot.py's on_text.

narration_filter.py has had a green suite since 2026-07-27 and changed nothing,
because nothing imported it. A passing unit suite on an unwired module is the
purest form of a gate that has never been asked a question. So this file tests
the WIRING, not the predicate:

  1. bot.py actually imports the filter and calls it inside on_text, behind the
     `first_text_sent` position gate. Asserted against bot.py's real source, so
     the test fails if someone removes the call.
  2. Replaying the 2026-08-14 incident through the same control flow yields ONE
     Slack post instead of nine.
  3. A turn whose ONLY block is filler still posts — the filter must never take
     a turn completely silent.

Run: python3 test_holding_filter_wiring.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from narration_filter import is_content_free_holding

BOT_PY = Path(__file__).with_name("bot.py")

# The nine blocks of the 2026-08-14 10:33-10:34 turn: one real deliverable
# followed by the eight content-free heartbeats the battery scored at -0.7.
INCIDENT_0814 = [
    "On it — 119 rows, ten parallel agents. Expect the table, not a progress log.",
    "Batch in. Waiting on the remaining 9.",
    "Holding for the remaining batches.",
    "Holding for the remaining 3 batches.",
    "Still 5 of 10. Holding for batches 5-9.",
    "Batches 5-9 still researching (rows 176-234).",
    "Two batches left. Holding.",
    "Only batch 9 (rows 224-234) left. Holding.",
    "Just batch 9 remaining.",
]

# A turn that must be completely unaffected: every block carries something.
CLEAN_TURN = [
    "On it — screening rows 116-234 now.",
    "Row 163 Gareth Sudul — sheet says COO at Anrok; Anrok's COO is someone else.",
    "Batch 7 failed — rerunning it.",
    "Done — 119 rows written. 55 Yes / 55 Maybe / 9 No.",
]


def replay(blocks: list[str]) -> list[str]:
    """Mirror of bot.py on_text's post/suppress decision. Returns what Slack
    would receive, in order."""
    posted: list[str] = []
    first_text_sent = False
    for block in blocks:
        if first_text_sent and is_content_free_holding(block):
            continue
        posted.append(block)
        first_text_sent = True
    return posted


def main() -> int:
    ok = True
    src = BOT_PY.read_text()

    # --- 1. the call site exists, and is position-gated -------------------
    if "from narration_filter import is_content_free_holding" not in src:
        print("FAIL: bot.py does not import is_content_free_holding")
        ok = False
    guard = re.search(
        r"if\s+first_text_sent\s+and\s+is_content_free_holding\(text_block\)\s*:",
        src,
    )
    if not guard:
        print("FAIL: bot.py on_text has no `if first_text_sent and "
              "is_content_free_holding(text_block):` guard")
        ok = False
    else:
        # The suppression must happen AFTER all_texts.append, so the audit
        # record keeps everything the model actually produced.
        append_at = src.find("all_texts.append(text_block)")
        if append_at == -1 or append_at > guard.start():
            print("FAIL: filter runs before all_texts.append — suppressed "
                  "blocks would vanish from the audit trail")
            ok = False

    # --- 2. the incident collapses to one message ------------------------
    posted = replay(INCIDENT_0814)
    if len(posted) != 1:
        print(f"FAIL: 08-14 incident posted {len(posted)} messages, expected 1")
        for p in posted[1:]:
            print(f"       leaked: {p!r}")
        ok = False
    elif posted[0] != INCIDENT_0814[0]:
        print(f"FAIL: wrong block survived: {posted[0]!r}")
        ok = False

    # --- 3. a turn of real blocks is untouched ---------------------------
    clean = replay(CLEAN_TURN)
    if clean != CLEAN_TURN:
        print("FAIL: clean turn was altered — filter is eating real content")
        for b in CLEAN_TURN:
            if b not in clean:
                print(f"       swallowed: {b!r}")
        ok = False

    # --- 4. never fully silent ------------------------------------------
    for solo in ("Holding.", "Just batch 9 remaining.", "Still 5 of 10."):
        if replay([solo]) != [solo]:
            print(f"FAIL: sole-block turn went silent on {solo!r}")
            ok = False

    print(f"08-14 incident: 9 blocks -> {len(posted)} Slack message(s). "
          f"Clean turn: {len(CLEAN_TURN)} -> {len(clean)}.")
    print("ALL PASS" if ok else "TESTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
