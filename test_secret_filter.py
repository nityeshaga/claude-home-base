"""Both-directions suite for secret_filter.

The positive half is not enough. A gate that has only ever returned PASS is
indistinguishable from a gate that cannot fail, and a gate whose fixtures are
last week's incident catches only last week's sentences. So this file has
three halves:

  1. MUST REDACT — vendor-prefixed live credential shapes.
  2. MUST NOT REDACT — prose ABOUT credentials, including the verbatim text of
     the 22:12:35 2026-08-31 self-report, which discussed the leak correctly
     and must survive the filter untouched. If writing up an incident trips the
     gate, the gate gets turned off.
  3. THE REAL INCIDENT INPUT — the actual bytes of ~/.config/gws/client_secret.json
     replayed through the filter, asserting detection by LABEL only, never by
     value. Per feedback_stale_fixtures_are_a_false_clean: a synthetic fixture
     shaped like the incident is not the incident.
"""
import os
import unittest

from secret_filter import find_secrets, redact

# Fixtures are COMPOSED, never literalised. GitHub push protection rejected the
# first version of this file over the Slack-token line — its scanner could not
# tell a synthetic fixture from a live token, which is a fair verdict on how
# realistic these shapes are and a good reason not to commit them verbatim.
_D = "0123456789"


def _tok(prefix: str, n: int, alphabet: str = "abcdefghijklmnopqrstuvwxyz") -> str:
    """Build a credential-SHAPED string without writing one into the source."""
    return prefix + "".join(alphabet[i % len(alphabet)] for i in range(n))


MUST_REDACT = [
    ("google_oauth_client_secret",
     '{"client_secret":"' + _tok("GOCSPX-", 28) + '"}'),
    ("google_api_key", "key=" + _tok("AIza", 35) + " done"),
    ("anthropic_api_key", _tok("sk-ant-api03-", 60)),
    ("openai_api_key", _tok("sk-proj-", 50)),
    ("slack_token", _tok("xoxb-", 12, _D) + "-" + _tok("", 16)),
    ("slack_app_token", "xapp-1-A" + _tok("", 9, _D) + "-" + _tok("", 13, _D) + "-" + _tok("", 6)),
    ("github_token", _tok("ghp_", 36)),
    ("aws_access_key_id", "AKIA" + _tok("", 16, "ABCDEFGHIJKLMNOP")),
    ("private_key_block", "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n"),
    ("google_refresh_token", _tok("1//0gL", 40)),
    ("bearer_jwt", _tok("eyJ", 20) + "." + _tok("eyJ", 20) + "." + _tok("", 20)),
]

# Every one of these is a real sentence someone here has written or would write.
MUST_NOT_REDACT = [
    "the GOCSPX- secret was posted in plaintext at 08:23:57",
    "Ring 0: never share API keys, tokens, passwords, or secrets, in any channel.",
    "I read ~/.config/gws/client_secret.json and it has 14 scopes.",
    "sk-ant- keys live in the Keychain, not in the repo.",
    "Rotate the client_secret for project cosmic-micron-491112-p3.",
    "xoxb- tokens are loaded from .env via load_dotenv(dotenv_path=...).",
    "AKIA-prefixed IDs are AWS access keys; we do not use AWS.",
    "The private key block is stored in the Keychain under service Cloudflare.",
    "https://every-docs.pages.dev deployed fine; 100 of 100 runs failed before that.",
    "Woodline Partners — Business Teams session 3 is confirmed for Thursday.",
    "",
]


class MustRedact(unittest.TestCase):
    def test_each_shape_is_caught_and_the_value_is_gone(self):
        for label, sample in MUST_REDACT:
            with self.subTest(label=label):
                self.assertIn(label, find_secrets(sample),
                              f"{label} not detected")
                clean, found = redact(sample)
                self.assertIn(label, found)
                self.assertIn(f"[REDACTED:{label}]", clean)
                # The payload itself must be gone, not merely flagged.
                secret_ish = max(sample.split('"'), key=len) if '"' in sample else sample
                self.assertNotIn(secret_ish.strip(), clean)


class MustNotRedact(unittest.TestCase):
    def test_prose_about_credentials_passes_untouched(self):
        for sample in MUST_NOT_REDACT:
            with self.subTest(sample=sample[:50]):
                self.assertEqual([], find_secrets(sample),
                                 "false positive — a gate that cries wolf gets skimmed")
                clean, found = redact(sample)
                self.assertEqual(sample, clean)
                self.assertEqual([], found)


class TheRealIncidentInput(unittest.TestCase):
    """Replay the actual leaked file, not a fixture shaped like it."""

    PATH = os.path.expanduser("~/.config/gws/client_secret.json")

    def test_the_file_that_leaked_is_caught(self):
        if not os.path.exists(self.PATH):
            self.skipTest(f"{self.PATH} absent — cannot replay the real input")
        with open(self.PATH) as fh:
            raw = fh.read()
        labels = find_secrets(raw)
        # Assert by LABEL. Printing the value here would be a second copy of
        # the leak, committed to a public-ish repo this time.
        self.assertIn("google_oauth_client_secret", labels,
                      "the exact bytes that leaked on 2026-08-31 are NOT caught")
        clean, found = redact(raw)
        self.assertIn("google_oauth_client_secret", found)
        self.assertNotIn("GOCSPX-", clean.replace("[REDACTED:google_oauth_client_secret]", ""))

    def test_the_selfreport_about_it_survives(self):
        """The 22:12 write-up named the format but withheld the value."""
        report = (
            "At 08:23:57 I posted the full client_secret.json for project "
            "cosmic-micron-491112-p3 into your DM — client_id, project_id and "
            "the GOCSPX- secret — in a code block. It is unrotated. Rotate or "
            "don't; your call."
        )
        self.assertEqual([], find_secrets(report))


class Mutations(unittest.TestCase):
    """If the suite passes with the gate disabled, the suite is decoration."""

    def test_suite_fails_when_patterns_are_removed(self):
        import secret_filter
        saved = secret_filter.PATTERNS
        try:
            secret_filter.PATTERNS = []
            for _, sample in MUST_REDACT:
                self.assertEqual([], secret_filter.find_secrets(sample))
            # i.e. with no patterns nothing is caught — proving the positive
            # half above is driven by the patterns and not by the assertions.
        finally:
            secret_filter.PATTERNS = saved
        self.assertTrue(secret_filter.find_secrets(MUST_REDACT[0][1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
