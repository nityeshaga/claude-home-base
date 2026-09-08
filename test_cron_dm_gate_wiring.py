"""Proves the gate is actually WIRED into bot.py's send path, not merely present.

A module that passes its own suite while nothing calls it is the 2026-08-17
failure: narration_filter sat unused for twenty-one days with a green suite
behind it. So this file asserts the integration, using the REAL recipient IDs
that the 09-06 and 08-11 incidents used, with the Slack client replaced by a
tripwire — if the gate is unwired, the tripwire fires instead of a DM landing in
a human's inbox at 4am.

Run: python3 test_cron_dm_gate_wiring.py
"""
import hashlib
import io
import logging
import os
import sys
from unittest import mock

# The gate reads os.environ at call time. Scrub the live-session markers so the
# import below cannot accidentally be classified as a live session.
for k in ("CLAUDE_THREAD_TS", "CLAUDE_CHANNEL_ID"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot  # noqa: E402

# ---------------------------------------------------------------------------
# The suite must not write to the canonical audit log.
#
# 2026-09-07: this file passed 11/11 while appending two real BLOCKED_CRON_DM
# records to audit.log naming Nityesh for DMs that were never attempted. The
# battery judge reads that file and ~/scripts/checks/cron-dm-gate.py counts
# those lines daily, so fixture records landed inside a live check's numbers.
# The two ALLOW-path tests had mocked audit_logger away; the REFUSE path had
# not. Mocking is the wrong fix in both directions -- it deletes the very
# assertion that a refusal gets recorded. So: divert every handler to an
# in-memory buffer, assert on the buffer, and prove at the end of the run that
# the real file is byte-identical. A test that corrupts the instrument it
# defends has not passed.
# ---------------------------------------------------------------------------
_AUDIT_BUF = io.StringIO()


def _divert(lg):
    """Strip a logger's file handlers and stop it propagating to its parent.

    Both halves matter. audit_logger is named "bot.audit", a CHILD of "bot",
    so removing its own handler still leaves every record propagating into
    bot.log through the parent's rotating handler -- and bot.log is the file
    the judge falls back to when audit.log is silent. Diverting one file and
    declaring the corruption fixed would be measuring the instrument I could
    reach cheaply instead of the one that matters.
    """
    for h in list(lg.handlers):
        lg.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    lg.propagate = False
    bh = logging.StreamHandler(_AUDIT_BUF)
    bh.setFormatter(logging.Formatter("%(asctime)s | %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S"))
    lg.addHandler(bh)


_divert(bot.audit_logger)   # audit.log
_divert(bot.logger)         # bot.log -- send_dm also logs the refusal here

_AUDIT_PATH = bot.AUDIT_LOG
_BOT_LOG_PATH = bot.LOG_DIR / "bot.log"
_MD5_BEFORE = {}
for _p in (_AUDIT_PATH, _BOT_LOG_PATH):
    _MD5_BEFORE[_p] = (hashlib.md5(_p.read_bytes()).hexdigest()
                       if _p.exists() else None)


def audit_records():
    return [ln for ln in _AUDIT_BUF.getvalue().splitlines() if ln.strip()]


NITYESH = "U0AH2TTHDK8"   # the 2026-09-06 22:07 recipient
RON = "U0AJVG699L0"       # the 2026-08-11 recipient

# Audit records are asserted against the in-memory buffer installed above, and
# test [6] proves the canonical file was never touched.
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok    {name}")
    else:
        FAILURES.append(f"{name} {detail}".strip())
        print(f"  FAIL  {name} {detail}")


class Tripwire:
    """Any attribute access is a Slack call that should not have happened."""

    def __getattr__(self, name):
        raise AssertionError(
            f"UNGATED SEND: bot.send_dm reached slack_client.{name}() from a "
            f"batch session. The gate is not wired."
        )


def test_real_module_is_imported_not_the_fallback():
    print("\n[1] bot.py imported the real module, not the degraded fallback")
    check("cron_dm_gate bound in bot", hasattr(bot, "cron_dm_gate"))
    check("it is the real module (has SANCTIONED_DELIVERABLES)",
          hasattr(bot.cron_dm_gate, "SANCTIONED_DELIVERABLES"))
    check("allowlist holds the two known subscriptions",
          set(bot.cron_dm_gate.SANCTIONED_DELIVERABLES) ==
          {"nityesh-daily-update", "ron-invoice-summary"},
          str(sorted(bot.cron_dm_gate.SANCTIONED_DELIVERABLES)))


def test_undeclared_batch_dm_never_touches_slack():
    print("\n[2] undeclared batch DM to the real 09-06 recipient")
    with mock.patch.object(bot, "slack_client", Tripwire()):
        try:
            result = bot.send_dm(NITYESH, "One thing about bot.py from the weekend")
        except AssertionError as e:
            check("no Slack call made", False, str(e))
            return
    check("send_dm returned None (refused)", result is None, repr(result))
    print("  ok    no Slack call made")
    check("the refusal was recorded",
          any("BLOCKED_CRON_DM" in r and NITYESH in r for r in audit_records()))


def test_wrong_recipient_for_a_sanctioned_deliverable_is_refused():
    print("\n[3] sanctioned deliverable aimed at the wrong human")
    with mock.patch.object(bot, "slack_client", Tripwire()):
        try:
            result = bot.send_dm(NITYESH, "invoice summary",
                                 deliverable="ron-invoice-summary")
        except AssertionError as e:
            check("no Slack call made", False, str(e))
            return
    check("send_dm returned None (refused)", result is None, repr(result))
    print("  ok    no Slack call made")


def test_sanctioned_delivery_does_reach_slack():
    print("\n[4] the sanctioned path is NOT blocked — proof the gate can say yes")
    fake = mock.MagicMock()
    fake.conversations_open.return_value = {"channel": {"id": "D0AP099BT25"}}
    with mock.patch.object(bot, "slack_client", fake), \
         mock.patch.object(bot, "post_response", return_value="1788746833.989429"), \
         mock.patch.object(bot, "_auto_upload_files"), \
         mock.patch.object(bot, "_save_session"):
        ts = bot.send_dm(RON, "Acme invoice sync — 2 sessions delivered.",
                         deliverable="ron-invoice-summary")
    check("returned a ts", ts == "1788746833.989429", repr(ts))
    check("opened the DM channel", fake.conversations_open.called)
    check("the allowed send was recorded",
          any("PROACTIVE_DM" in r and RON in r for r in audit_records()))

    # The exact send nityesh-daily-update.sh:63 makes. Asserted because adding
    # the gate BROKE this delivery until --deliverable was threaded into the
    # wrapper: a gate that refuses the right turn fails silently, in the
    # safe-looking direction, and nothing surfaces it.
    fake2 = mock.MagicMock()
    fake2.conversations_open.return_value = {"channel": {"id": "D0AH2TTHDK8"}}
    with mock.patch.object(bot, "slack_client", fake2), \
         mock.patch.object(bot, "post_response", return_value="1788800000.000001"), \
         mock.patch.object(bot, "_auto_upload_files"), \
         mock.patch.object(bot, "_save_session"):
        ts2 = bot.send_dm(NITYESH, "Changelog for 2026-09-07: 3 commits.",
                          deliverable="nityesh-daily-update")
    check("nityesh-daily-update delivery still goes out", ts2 == "1788800000.000001", repr(ts2))


def test_live_session_dm_still_works():
    print("\n[5] a live Slack session can still DM (cross-thread forward pattern)")
    fake = mock.MagicMock()
    fake.conversations_open.return_value = {"channel": {"id": "D0AGB2UA13P"}}
    with mock.patch.dict(os.environ, {"CLAUDE_THREAD_TS": "1788553558.986559"}), \
         mock.patch.object(bot, "slack_client", fake), \
         mock.patch.object(bot, "post_response", return_value="1788553999.000100"), \
         mock.patch.object(bot, "_auto_upload_files"), \
         mock.patch.object(bot, "_save_session"):
        ts = bot.send_dm("U0AH8J541RA", "Quick question — use updated pricing?")
    check("returned a ts", ts == "1788553999.000100", repr(ts))


def test_canonical_audit_log_untouched():
    """The 2026-09-07 defect, as an assertion.

    Every record this suite generates must be in the buffer and none in the
    file. Checked by content hash rather than line count so a same-length
    mutation cannot pass.
    """
    print("\n[6] no canonical log file was written to by this suite")
    for path, before in _MD5_BEFORE.items():
        after = (hashlib.md5(path.read_bytes()).hexdigest()
                 if path.exists() else None)
        check(f"{path.name} md5 unchanged",
              after == before, f"before={before} after={after}")
    recs = audit_records()
    check("the suite did generate audit records (buffer is not vacuous)",
          len(recs) >= 2, f"{len(recs)} record(s)")
    print(f"  info  {len(recs)} record(s) captured in-memory, 0 written to disk")


if __name__ == "__main__":
    test_real_module_is_imported_not_the_fallback()
    test_undeclared_batch_dm_never_touches_slack()
    test_wrong_recipient_for_a_sanctioned_deliverable_is_refused()
    test_sanctioned_delivery_does_reach_slack()
    test_live_session_dm_still_works()
    test_canonical_audit_log_untouched()
    print()
    if FAILURES:
        print(f"RESULT FAILED — {len(FAILURES)} assertion(s):")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("RESULT PASSED — gate is wired into bot.send_dm, both directions")
