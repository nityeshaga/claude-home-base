"""Both-directions tests for the reconnect backlog sweep.

A gate that has only ever returned "fire" is indistinguishable from a gate that
cannot stay quiet, and vice versa. So every behaviour here is tested in both
directions, and the last class of test replays the verbatim messages from the
2026-08-21..25 outage this module was written for — a suite that only knows
synthetic fixtures is a false clean.
"""

import json
import tempfile
import unittest
from pathlib import Path

import reconnect_sweep as rs


ROSTER = {"U_TEAMMATE_A", "U_TEAMMATE_B"}  # two teammates on the roster
BOT = "U_BOT"


def msg(ts, user=None, text="", replies=0, files=None, bot=False, subtype=None):
    m = {"ts": str(ts), "text": text, "reply_count": replies}
    if bot:
        m["bot_id"] = "B123"
    if user:
        m["user"] = user
    if files:
        m["files"] = [{"name": n} for n in files]
    if subtype:
        m["subtype"] = subtype
    return m


class FakeClient:
    def __init__(self, conversations, history):
        self._conversations = conversations
        self._history = history
        self.posted = []

    def conversations_list(self, **kwargs):
        return {"channels": self._conversations, "response_metadata": {}}

    def conversations_history(self, channel, **kwargs):
        return {"messages": self._history.get(channel, [])}

    def chat_postMessage(self, channel, text, thread_ts=None):
        self.posted.append({"channel": channel, "text": text, "thread_ts": thread_ts})
        return {"ok": True}


class StateIsolated(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = rs.STATE_FILE
        rs.STATE_FILE = Path(self._tmp.name) / ".reconnect_state.json"

    def tearDown(self):
        rs.STATE_FILE = self._orig
        self._tmp.cleanup()


class TestOutageDetection(StateIsolated):
    def test_first_run_is_not_an_outage(self):
        # No watermark must not read as a four-decade outage.
        self.assertIsNone(rs.downtime_seconds())
        self.assertFalse(rs.is_outage(None))

    def test_normal_restart_stays_quiet(self):
        self.assertFalse(rs.is_outage(60))
        self.assertFalse(rs.is_outage(rs.MIN_DOWNTIME_SECONDS - 1))

    def test_real_outage_fires(self):
        self.assertTrue(rs.is_outage(rs.MIN_DOWNTIME_SECONDS))
        self.assertTrue(rs.is_outage(4 * 86400))

    def test_watermark_roundtrip(self):
        rs.touch(now=1000.0)
        self.assertEqual(rs.last_seen(), 1000.0)
        self.assertAlmostEqual(rs.downtime_seconds(now=1500.0), 500.0)


class TestUnansweredFilter(StateIsolated):
    def test_picks_up_genuinely_ignored_message(self):
        got = rs.unanswered_in([msg(5, "U_TEAMMATE_A", "hi")], ROSTER, set())
        self.assertEqual(len(got), 1)

    def test_answered_message_is_not_backlog(self):
        # Bot replies land in threads, so reply_count is the answered signal.
        got = rs.unanswered_in([msg(5, "U_TEAMMATE_A", "hi", replies=3)], ROSTER, set())
        self.assertEqual(got, [])

    def test_bot_own_messages_are_not_backlog(self):
        got = rs.unanswered_in([msg(5, BOT, "hello", bot=True)], ROSTER, set())
        self.assertEqual(got, [])

    def test_off_roster_human_is_not_backlog(self):
        got = rs.unanswered_in([msg(5, "U0STRANGER", "hi")], ROSTER, set())
        self.assertEqual(got, [])

    def test_join_leave_subtypes_are_not_backlog(self):
        got = rs.unanswered_in(
            [msg(5, "U_TEAMMATE_A", "joined", subtype="channel_join")], ROSTER, set()
        )
        self.assertEqual(got, [])

    def test_already_notified_is_not_backlog_again(self):
        got = rs.unanswered_in([msg(5, "U_TEAMMATE_A", "hi")], ROSTER, {"5"})
        self.assertEqual(got, [])

    def test_results_are_oldest_first(self):
        got = rs.unanswered_in(
            [msg(9, "U_TEAMMATE_A"), msg(3, "U_TEAMMATE_A"), msg(6, "U_TEAMMATE_A")],
            ROSTER, set(),
        )
        self.assertEqual([m["ts"] for m in got], ["3", "6", "9"])


class TestNotice(StateIsolated):
    def test_names_the_attachment_it_never_opened(self):
        text = rs.compose_notice([msg(5, "U_TEAMMATE_A", files=["Deck.pdf"])], 4 * 86400)
        self.assertIn("Deck.pdf", text)

    def test_no_attachment_line_when_there_are_no_files(self):
        text = rs.compose_notice([msg(5, "U_TEAMMATE_A")], 3600)
        self.assertNotIn("attachment", text)

    def test_window_reads_in_days_for_long_outages(self):
        self.assertIn("4 days", rs.compose_notice([msg(5, "U_TEAMMATE_A")], 4 * 86400))
        self.assertIn("3 hours", rs.compose_notice([msg(5, "U_TEAMMATE_A")], 3 * 3600))

    def test_does_not_put_the_burden_back_on_the_sender(self):
        # The failure being fixed was answering "what do you need?" to someone
        # who had already asked, with links, and been met with silence.
        text = rs.compose_notice([msg(5, "U_TEAMMATE_A")], 4 * 86400).lower()
        self.assertNotIn("what do you need", text)
        self.assertIn("on me", text)


class TestSweep(StateIsolated):
    def _client(self):
        return FakeClient(
            [{"id": "D_A"}, {"id": "D_QUIET"}],
            {
                "D_A": [msg(100, "U_TEAMMATE_A", "hi"), msg(90, "U_TEAMMATE_A", "hey")],
                "D_QUIET": [msg(80, "U_TEAMMATE_B", "answered", replies=2)],
            },
        )

    def test_notifies_once_per_conversation_on_the_earliest_message(self):
        c = self._client()
        notices = rs.run_sweep(c, ROSTER, 4 * 86400, now=200)
        self.assertEqual(len(notices), 1)
        self.assertEqual(len(c.posted), 1)
        self.assertEqual(c.posted[0]["channel"], "D_A")
        self.assertEqual(c.posted[0]["thread_ts"], "90")  # oldest, where the ask was

    def test_conversation_with_nothing_missed_gets_no_post(self):
        c = self._client()
        rs.run_sweep(c, ROSTER, 4 * 86400, now=200)
        self.assertNotIn("D_QUIET", [p["channel"] for p in c.posted])

    def test_second_sweep_is_silent(self):
        c = self._client()
        rs.run_sweep(c, ROSTER, 4 * 86400, now=200)
        c2 = self._client()
        self.assertEqual(rs.run_sweep(c2, ROSTER, 4 * 86400, now=200), [])
        self.assertEqual(c2.posted, [])

    def test_dry_run_posts_nothing_but_still_reports(self):
        c = self._client()
        notices = rs.run_sweep(c, ROSTER, 4 * 86400, dry_run=True, now=200)
        self.assertEqual(len(notices), 1)
        self.assertEqual(c.posted, [])

    def test_empty_conversation_list_is_not_a_clean_result(self):
        # A sweep that scans nothing must not look like a sweep that found nothing.
        c = FakeClient([], {})
        with self.assertLogs("bot.reconnect", level="WARNING") as log:
            self.assertEqual(rs.run_sweep(c, ROSTER, 4 * 86400, now=200), [])
        self.assertTrue(any("not a clean result" in line for line in log.output))

    def test_one_broken_channel_does_not_kill_the_sweep(self):
        class Flaky(FakeClient):
            def conversations_history(self, channel, **kwargs):
                if channel == "D_BROKEN":
                    raise RuntimeError("channel_not_found")
                return super().conversations_history(channel, **kwargs)

        c = Flaky(
            [{"id": "D_BROKEN"}, {"id": "D_A"}],
            {"D_A": [msg(100, "U_TEAMMATE_A", "hi")]},
        )
        notices = rs.run_sweep(c, ROSTER, 4 * 86400, now=200)
        self.assertEqual([n["channel"] for n in notices], ["D_A"])


class TestActualIncident(StateIsolated):
    """Replay of the real four-day-outage backlog, shape and timestamps intact.

    A suite that only knows fixtures its author invented is a false clean. These
    are the actual message timings from the incident this module was written
    for; only the identifiers are placeholders. If it cannot catch that, the
    synthetic tests above are noise.
    """

    TEAMMATE_BACKLOG = [
        msg(1787331781.890429, "U_TEAMMATE_A", "hey can you read this <@U_BOT>?",
            files=["Q3-Deck.pdf"]),
        msg(1787331798.961849, "U_TEAMMATE_A", "hi"),
        msg(1787339045.405619, "U_TEAMMATE_A", "hi"),
        msg(1787339979.921349, "U_TEAMMATE_A", "hi"),
        msg(1787339982.077859, "U_TEAMMATE_A", "<@U_BOT>"),
        msg(1787582553.623929, "U_TEAMMATE_A", "hi"),
        msg(1787670495.176199, "U_TEAMMATE_A", "hi"),
        # The one that WAS answered, 4 seconds after reconnect.
        msg(1787682716.190489, "U_TEAMMATE_A", "Hi", replies=1),
    ]

    def test_catches_all_seven_and_not_the_answered_one(self):
        got = rs.unanswered_in(self.TEAMMATE_BACKLOG, ROSTER, set())
        self.assertEqual(len(got), 7)
        self.assertNotIn("1787682716.190489", [m["ts"] for m in got])

    def test_threads_the_notice_on_the_deck_message(self):
        c = FakeClient([{"id": "D_TEAMMATE_A"}], {"D_TEAMMATE_A": self.TEAMMATE_BACKLOG})
        notices = rs.run_sweep(c, ROSTER, 4 * 86400, now=1787682716.0)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["count"], 7)
        # The earliest unanswered message is the substantive one with the deck.
        self.assertEqual(c.posted[0]["thread_ts"], "1787331781.890429")
        self.assertIn("Q3-Deck.pdf", c.posted[0]["text"])

    def test_the_outage_gap_would_have_triggered_it(self):
        # bot heartbeat last written ~2026-08-21 13:00 ET, process back 08-25 14:24 ET.
        self.assertTrue(rs.is_outage(1787682287 - 1787331600))


if __name__ == "__main__":
    unittest.main(verbosity=2)
