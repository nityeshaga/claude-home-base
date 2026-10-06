"""Notepad tests. Run: python3 -m unittest discover -s tests (from the notepad directory).
Every test uses a temp database and a temp closed-items ledger, never the real ones."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from multiprocessing import get_context

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin", "notepad")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "claude_result.json")
sys.path.insert(0, ROOT)
import notepad as np  # noqa: E402

LEDGER = """| date | user | match terms | their words |
|---|---|---|---|
| 2026-01-11 | alice | vendor + renewal | "It is done." |
| 2026-01-12 | both | gcp + billing | "remove the gcp billing thing" |
"""

AGENT = dict(added_by="agent:email", waiting="Mom", action_label="Draft replies for me",
             action_instruction="Draft replies to Mom's three emails.", department="email")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        ledger = os.path.join(self.tmp.name, "closed.md")
        with open(ledger, "w") as f:
            f.write(LEDGER)
        cfg = os.path.join(self.tmp.name, "config.json")
        with open(cfg, "w") as f:
            json.dump({"people": {"alice": {}, "bob": {}}}, f)
        self.env = {"NOTEPAD_DB": self.db, "NOTEPAD_CLOSED_LEDGER": ledger, "NOTEPAD_CONFIG": cfg}
        self.saved = {k: os.environ.get(k) for k in list(self.env) + ["NOTEPAD_READONLY_FOR", "NOTEPAD_ACTOR"]}
        os.environ.update(self.env)
        os.environ.pop("NOTEPAD_READONLY_FOR", None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def cli(self, *args):
        env = dict(os.environ, NOTEPAD_ACTOR="test")
        p = subprocess.run([sys.executable, BIN, *args], capture_output=True, text=True, env=env)
        return p.returncode, p.stdout, p.stderr

    def cli_json(self, *args):
        code, out, err = self.cli(*args, "--json")
        self.assertEqual(code, 0, out + err)
        return json.loads(out)


class Rules(Base):
    def test_rule1_entry_test(self):
        for missing in ("waiting", "action_label", "action_instruction"):
            kw = dict(AGENT, **{missing: None})
            with self.assertRaises(np.Refused) as c:
                np.add_item("alice", "Mom wrote three times", **kw)
            self.assertIn(missing, str(c.exception))
        with self.assertRaises(np.Refused):
            np.add_item("alice", "  ", **AGENT)
        self.assertEqual(np.add_item("alice", "Mom wrote three times", **AGENT)["status"], "open")

    def test_rule2_persons_own_item(self):
        i = np.add_item("alice", "Improve the search index", added_by="alice", actor="alice")
        self.assertEqual(i["waiting"], "alice")
        self.assertIsNone(i["action_label"])
        with self.assertRaises(np.Refused):
            np.add_item("alice", "Call the bank", added_by="alice", actor="session:abc")
        i = np.add_item("alice", "Call the bank", added_by="alice", actor="session:abc",
                        quote="put calling the bank on my notepad")
        self.assertEqual(i["quote"], "put calling the bank on my notepad")
        with self.assertRaises(np.Refused):
            np.add_item("alice", "x", added_by="somebody")

    def test_rule3_closed_topics(self):
        with self.assertRaises(np.Refused) as c:
            np.add_item("alice", "Follow up on the vendor renewal conversation", **AGENT)
        self.assertIn("It is done", str(c.exception))
        # the ban is hers, not Bob's
        np.add_item("bob", "Follow up on the vendor renewal conversation", **AGENT)
        # 'both' rows apply to both; the action instruction is checked too
        for person in ("alice", "bob"):
            with self.assertRaises(np.Refused):
                np.add_item(person, "Money thing", **dict(AGENT, action_instruction="Fix the GCP billing alert"))
        # a person's own items are checked as well
        with self.assertRaises(np.Refused):
            np.add_item("alice", "vendor renewal", added_by="alice", actor="alice")
        # an update cannot smuggle a closed topic in
        i = np.add_item("alice", "Mom wrote", **AGENT)
        with self.assertRaises(np.Refused):
            np.update_item(i["id"], line="Vendor renewal follow-up")

    def test_rule4_kill_switch(self):
        i = np.add_item("alice", "Mom wrote", **AGENT)
        os.environ["NOTEPAD_READONLY_FOR"] = "alice"
        for fn in (lambda: np.add_item("alice", "Mom again", **AGENT),
                   lambda: np.close_item(i["id"], "handled"),
                   lambda: np.update_item(i["id"], rank=1),
                   lambda: np.mark_seen(i["id"]),
                   lambda: np.attach_session(i["id"], status="working"),
                   lambda: np.set_pref("alice", "k", "v"),
                   lambda: np.start_run("email", "alice"),
                   lambda: np.log_event("x", actor="t", item_id=i["id"])):
            with self.assertRaises(np.Refused):
                fn()
        np.add_item("bob", "Hetzner invoice", **AGENT)  # bob is unaffected
        self.assertEqual(len(np.list_items("alice")), 1)  # reads still work

    def test_rule5_every_change_has_one_event(self):
        i = np.add_item("alice", "Mom wrote", **AGENT)
        steps = [lambda: np.update_item(i["id"], standing="drafted"), lambda: np.mark_seen(i["id"]),
                 lambda: np.attach_session(i["id"], session_id="s1"), lambda: np.close_item(i["id"], "handled")]
        for n, step in enumerate(steps, start=2):
            step()
            self.assertEqual(len(np.events(item_id=i["id"])), n)
        self.assertEqual([e["action"] for e in np.events(item_id=i["id"])],
                         ["item_added", "item_updated", "item_seen", "session_attached", "item_closed"])

    def test_rule5_refusal_writes_nothing(self):
        with self.assertRaises(np.Refused):
            np.add_item("alice", "Mom", **dict(AGENT, waiting=None))
        self.assertEqual(np.events(), [])

    def test_rule5_event_rolls_back_with_change(self):
        i = np.add_item("alice", "Mom wrote", **AGENT)
        np.close_item(i["id"], "handled")
        with self.assertRaises(np.Refused):
            np.close_item(i["id"], "stale")  # already closed: no change, no event
        self.assertEqual(len(np.events(item_id=i["id"])), 2)

    def test_rule6_source_ref_dedupe(self):
        a = np.add_item("alice", "Mom wrote", source_ref="gmail-thread:1", **AGENT)
        b = np.add_item("alice", "Mom wrote again", source_ref="gmail-thread:1", rank=5, **AGENT)
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b["deduped"])
        self.assertEqual((b["line"], b["rank"]), ("Mom wrote again", 5))
        self.assertEqual(len(np.list_items("alice")), 1)
        # other department or other person is a different item
        np.add_item("alice", "Mom", source_ref="gmail-thread:1", **dict(AGENT, department="calendar"))
        np.add_item("bob", "Mom", source_ref="gmail-thread:1", **AGENT)
        self.assertEqual(len(np.list_items("alice")), 2)
        # once closed, the same source opens a new item
        np.close_item(a["id"], "handled")
        c = np.add_item("alice", "Mom wrote a fourth time", source_ref="gmail-thread:1", **AGENT)
        self.assertNotEqual(c["id"], a["id"])
        # the database refuses a duplicate even without the Python check
        conn = sqlite3.connect(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO items(person, department, waiting, line, added_by, source_ref, created_at, "
                         "updated_at) VALUES ('alice','email','x','x','agent:email','gmail-thread:1','t','t')")

    def test_rule7_closing(self):
        expect = {"handled": "dealt_with", "dismissed": "dealt_with", "evidence": "dealt_with",
                  "superseded": "superseded", "stale": "stale"}
        for how, status in expect.items():
            i = np.add_item("alice", f"item {how}", **AGENT)
            c = np.close_item(i["id"], how, "because")
            self.assertEqual((c["status"], c["closed_how"], c["closed_why"]), (status, how, "because"))
            self.assertTrue(c["closed_at"])
        with self.assertRaises(ValueError):
            np.close_item(i["id"], "dealt_with")
        self.assertEqual(len(np.recent_dismissals("alice")), 1)
        self.assertEqual(np.list_items("alice"), [])


class NoConfig(Base):
    def test_any_name_is_a_person_without_config(self):
        os.environ["NOTEPAD_CONFIG"] = os.path.join(self.tmp.name, "absent.json")
        self.assertEqual(np.people(), ())
        self.assertEqual(np.add_item("carol", "Renew the domain", added_by="carol", actor="carol")["waiting"], "carol")
        self.assertEqual(np.add_item("carol", "Mom wrote", **AGENT)["person"], "carol")
        with self.assertRaises(np.Refused):
            np.add_item("carol", "x", added_by="session:abc")
        with self.assertRaises(ValueError):
            np.add_item("agent:email", "x", **AGENT)

    def test_missing_ledger_closes_nothing(self):
        os.environ["NOTEPAD_CLOSED_LEDGER"] = os.path.join(self.tmp.name, "no-ledger.md")
        self.assertEqual(np.add_item("alice", "Follow up on the vendor renewal conversation", **AGENT)["status"], "open")


class EventsAppendOnly(Base):
    def test_update_and_delete_abort(self):
        np.log_event("email_archived", actor="t", detail={"id": "m1"})
        conn = sqlite3.connect(self.db)
        for sql in ("UPDATE events SET action='x'", "DELETE FROM events"):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(sql)
        self.assertEqual(np.events()[0]["detail"], {"id": "m1"})

    def test_wal(self):
        np.list_items("alice")
        self.assertEqual(sqlite3.connect(self.db).execute("PRAGMA journal_mode").fetchone()[0], "wal")


class Commands(Base):
    def add_agent(self, *extra):
        return self.cli_json("add", "--for", "alice", "--by", "agent:email", "--waiting", "Mom",
                             "--line", "Mom wrote three times", "--action", "Draft replies for me::Draft them.",
                             "--dept", "email", *extra)

    def test_add_list_show(self):
        i = self.add_agent("--since", "2026-09-22", "--rank", "10", "--source", "gmail-thread:a",
                           "--link", "https://x", "--session", "s1", "--shared")
        self.assertEqual((i["waiting_since"], i["rank"], i["session_is_shared"], i["action_label"]),
                         ("2026-09-22", 10, 1, "Draft replies for me"))
        self.assertEqual(self.cli_json("show", str(i["id"]))["line"], "Mom wrote three times")
        self.assertEqual(len(self.cli_json("list", "--for", "alice")), 1)
        code, out, _ = self.cli("list", "--for", "alice")
        self.assertIn("Mom wrote three times", out)
        self.assertEqual(self.add_agent("--source", "gmail-thread:a")["id"], i["id"])

    def test_refusals_exit_2(self):
        code, out, _ = self.cli("add", "--for", "alice", "--by", "agent:email", "--waiting", "Mom", "--line", "x")
        self.assertEqual(code, 2)
        self.assertIn("action_label", out)
        code, out, _ = self.cli("add", "--for", "alice", "--by", "agent:email", "--waiting", "Mom",
                                "--line", "x", "--json")
        self.assertEqual((code, json.loads(out)["ok"]), (2, False))

    def test_errors_exit_1(self):
        self.assertEqual(self.cli("show", "999")[0], 1)
        self.assertEqual(self.cli("add", "--for", "alice", "--by", "agent:email", "--waiting", "M",
                                  "--line", "x", "--action", "no separator")[0], 1)

    def test_own_add_someday_promote(self):
        i = self.cli_json("add", "--for", "alice", "--by", "alice", "--line", "Check QMD", "--someday",
                          "--quote", "put it on my someday list")
        self.assertEqual((i["kind"], i["waiting"]), ("someday", "alice"))
        self.assertEqual(self.cli_json("list", "--for", "alice"), [])
        self.assertEqual(len(self.cli_json("list", "--for", "alice", "--someday")), 1)
        self.assertEqual([x["kind"] for x in self.cli_json("list", "--for", "alice", "--all")], ["someday"])
        code, out, _ = self.cli("list", "--for", "alice", "--all")
        self.assertIn("Check QMD", out)
        self.assertIn("[someday]", out)
        self.assertEqual(self.cli("list", "--for", "alice")[1].strip(), "(nothing)")
        self.assertEqual(self.cli_json("promote", str(i["id"]))["kind"], "needs_you")
        self.assertEqual(self.cli("add", "--for", "alice", "--by", "alice", "--line", "x",
                                  "--actor", "session:abc")[0], 2)
        self.assertEqual(self.cli("add", "--for", "alice", "--by", "alice", "--line", "x",
                                  "--actor", "alice")[0], 0)

    def test_update_attach_seen_done_dismiss(self):
        i = self.add_agent()
        n = str(i["id"])
        u = self.cli_json("update", n, "--line", "Mom, 3 emails", "--action", "Reply::Reply to Mom",
                          "--rank", "3", "--standing", "drafted two", "--link", "https://y")
        self.assertEqual((u["line"], u["action_label"], u["rank"], u["standing"]), ("Mom, 3 emails", "Reply", 3,
                                                                                    "drafted two"))
        a = self.cli_json("attach", n, "--channel", "D1", "--thread", "1.2", "--session", "s", "--own",
                          "--status", "working")
        self.assertEqual((a["slack_channel"], a["status"], a["session_is_shared"]), ("D1", "working", 0))
        self.assertTrue(self.cli_json("seen", n)["seen_at"])
        self.assertEqual(self.cli_json("done", n, "--how", "evidence", "--why", "he replied")["status"], "dealt_with")
        j = self.add_agent()
        self.assertEqual(self.cli_json("dismiss", str(j["id"]))["closed_how"], "dismissed")
        self.assertEqual(len(self.cli_json("dismissals", "--for", "alice", "--days", "1")), 1)
        self.assertEqual(len(self.cli_json("list", "--for", "alice", "--all")), 2)
        self.assertEqual(self.cli_json("log", "--item", n)[0]["actor"], "test")

    def test_prefs(self):
        self.cli_json("prefs", "set", "--for", "alice", "dm_time", "08:00", "--quote", "8 is fine")
        self.assertEqual(self.cli_json("prefs", "get", "--for", "alice", "dm_time")["value"], "08:00")
        self.cli_json("prefs", "set", "--for", "alice", "dm_time", "07:45")
        self.assertEqual([p["value"] for p in self.cli_json("prefs", "list", "--for", "alice")], ["07:45"])
        self.assertEqual(len(self.cli_json("log", "--action", "pref_set")), 2)

    def test_event_and_log(self):
        rid = self.cli_json("run", "start", "--dept", "email", "--for", "alice")["id"]
        self.cli_json("event", "--action", "email_archived", "--run", str(rid),
                      "--detail", '{"id":"m1","from":"a","subject":"s","reason":"promo"}')
        rows = self.cli_json("log", "--run", str(rid), "--action", "email_archived")
        self.assertEqual(rows[0]["detail"]["reason"], "promo")
        self.assertEqual(self.cli("event", "--action", "x", "--detail", "not json")[0], 1)
        self.assertEqual(self.cli_json("log", "--since", "2000-01-01")[0]["action"], "run_started")

    def test_runs_from_result(self):
        rid = self.cli_json("run", "start", "--dept", "email", "--for", "alice", "--model", "claude-opus-5-5",
                            "--effort", "medium", "--mode", "list-only")["id"]
        self.add_agent()
        r = self.cli_json("run", "finish", str(rid), "--status", "ok", "--from-result", FIXTURE,
                          "--archived", "4", "--note", "fine")
        self.assertEqual((r["tokens_in"], r["tokens_out"], r["tokens_cache_read"], r["tokens_cache_write"]),
                         (6 + 36461 + 35022, 158, 36461, 35022))
        self.assertEqual((r["subagents"], r["seconds"], r["emails_archived"], r["items_added"], r["status"]),
                         (1, 5, 4, 1, "ok"))
        self.assertAlmostEqual(r["cost_usd"], 0.2326502)
        self.assertEqual(r["session_id"], "5436a2be-dc51-4597-bf8a-74e83bc45d20")
        self.assertEqual(self.cli_json("run", "last", "--dept", "email")["id"], rid)
        self.assertEqual(self.cli("run", "finish", str(rid), "--status", "ok")[0], 2)  # finished already

    def test_default_actor(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("NOTEPAD_ACTOR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}
        run = lambda extra: json.loads(subprocess.run(
            [sys.executable, BIN, "event", "--action", "x", "--json"], env=dict(env, **extra),
            capture_output=True, text=True).stdout)["id"]
        run({})
        run({"CLAUDE_SESSION_ID": "abc"})
        run({"NOTEPAD_ACTOR": "agent:email", "CLAUDE_SESSION_ID": "abc"})
        self.assertEqual([e["actor"] for e in np.events()], ["unknown", "session:abc", "agent:email"])


def _writer(args):
    db, ledger, n, count = args
    os.environ["NOTEPAD_DB"], os.environ["NOTEPAD_CLOSED_LEDGER"] = db, ledger
    os.environ["NOTEPAD_CONFIG"] = os.path.join(os.path.dirname(db), "config.json")
    import notepad as mod
    for k in range(count):
        mod.add_item("bob", f"writer {n} item {k}", source_ref=f"w{n}-{k}", **AGENT)
        # same source from every writer: must collapse to one item
        mod.add_item("bob", "shared thread", source_ref="shared", **AGENT)
    return n


class Concurrency(Base):
    def test_parallel_writers(self):
        writers, count = 8, 25
        ledger = os.environ["NOTEPAD_CLOSED_LEDGER"]
        # nothing created up front: the processes also race to create the schema
        with get_context("spawn").Pool(writers) as pool:
            done = pool.map(_writer, [(self.db, ledger, n, count) for n in range(writers)])
        self.assertEqual(sorted(done), list(range(writers)))
        items = np.list_items("bob")
        self.assertEqual(len(items), writers * count + 1)
        self.assertEqual(len(np.events(action="item_added", limit=10000)), writers * count + 1)
        self.assertEqual(len(np.events(action="item_readded", limit=10000)), writers * count - 1)

    def test_parallel_cli(self):
        procs = [subprocess.Popen([sys.executable, BIN, "add", "--for", "bob", "--by", "agent:email",
                                   "--waiting", "W", "--line", f"cli {n}", "--action", "A::B"],
                                  env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for n in range(12)]
        self.assertEqual([p.communicate() and p.returncode for p in procs], [0] * 12)
        self.assertEqual(len(np.list_items("bob")), 12)


if __name__ == "__main__":
    unittest.main()
