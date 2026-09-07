"""Proves the gate is actually WIRED into bot.py's send path, not merely present.

A module that passes its own suite while nothing calls it is the 2026-08-17
failure: narration_filter sat unused for twenty-one days with a green suite
behind it. So this file asserts the integration, using the REAL recipient IDs
that the 09-06 and 08-11 incidents used, with the Slack client replaced by a
tripwire — if the gate is unwired, the tripwire fires instead of a DM landing in
a human's inbox at 4am.

Run: python3 test_cron_dm_gate_wiring.py
"""
import os
import sys
from unittest import mock

# The gate reads os.environ at call time. Scrub the live-session markers so the
# import below cannot accidentally be classified as a live session.
for k in ("CLAUDE_THREAD_TS", "CLAUDE_CHANNEL_ID"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot  # noqa: E402

NITYESH = "U0AH2TTHDK8"   # the 2026-09-06 22:07 recipient
RON = "U0AJVG699L0"       # the 2026-08-11 recipient

# audit_logger is mocked in the two ALLOW-path tests below. Without that, a
# green test run forges PROACTIVE_DM lines in audit.log naming real recipients,
# and audit.log is the canonical record the battery judge reads. A suite that
# corrupts the instrument it is meant to protect is not a passing suite.
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
         mock.patch.object(bot, "audit_logger", mock.MagicMock()), \
         mock.patch.object(bot, "_save_session"):
        ts = bot.send_dm(RON, "Acme invoice sync — 2 sessions delivered.",
                         deliverable="ron-invoice-summary")
    check("returned a ts", ts == "1788746833.989429", repr(ts))
    check("opened the DM channel", fake.conversations_open.called)

    # The exact send nityesh-daily-update.sh:63 makes. Asserted because adding
    # the gate BROKE this delivery until --deliverable was threaded into the
    # wrapper: a gate that refuses the right turn fails silently, in the
    # safe-looking direction, and nothing surfaces it.
    fake2 = mock.MagicMock()
    fake2.conversations_open.return_value = {"channel": {"id": "D0AH2TTHDK8"}}
    with mock.patch.object(bot, "slack_client", fake2), \
         mock.patch.object(bot, "post_response", return_value="1788800000.000001"), \
         mock.patch.object(bot, "_auto_upload_files"), \
         mock.patch.object(bot, "audit_logger", mock.MagicMock()), \
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
         mock.patch.object(bot, "audit_logger", mock.MagicMock()), \
         mock.patch.object(bot, "_save_session"):
        ts = bot.send_dm("U0AH8J541RA", "Quick question — use updated pricing?")
    check("returned a ts", ts == "1788553999.000100", repr(ts))


if __name__ == "__main__":
    test_real_module_is_imported_not_the_fallback()
    test_undeclared_batch_dm_never_touches_slack()
    test_wrong_recipient_for_a_sanctioned_deliverable_is_refused()
    test_sanctioned_delivery_does_reach_slack()
    test_live_session_dm_still_works()
    print()
    if FAILURES:
        print(f"RESULT FAILED — {len(FAILURES)} assertion(s):")
        for f in FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("RESULT PASSED — gate is wired into bot.send_dm, both directions")
