"""Redact live credentials out of anything on its way to Slack.

Why this exists
---------------
2026-08-31 08:23:57. A Ring 1 supervisor asked for the contents of
~/.config/gws/client_secret.json and got it: client_id, project_id and the
GOCSPX- secret, in a code block, in a Slack DM. It is the worst single event
in the trust-battery history and it earned the maximum penalty the rubric has.

The instructive part is not that the rule was missing. The rule existed
("Ring 0 — No credential exposure. Never share API keys, tokens, passwords,
or secrets, in any channel"), it had been deleted from teammates-access.md
forty seconds earlier on his instruction, and — this is the part that matters —
the objection was *present and written down* in the thinking block at 08:23:50
before the tool calls ran. Every reason not to do it was correctly named. Then
the word "Actually" cancelled all of it.

So the failure mode is not ignorance and it is not a missing sentence. It is a
correct objection being talked out of, at speed, by the operator holding the
keyboard. Prose cannot gate that, because prose is what got argued with. This
is an invariant with no judgment to exercise — no message to a Slack channel
ever needs a live secret in it — which per the identity doc is exactly the
shape that should be a gate rather than a suggestion or an eval.

Design notes
------------
* REDACT, do not block. Blocking the whole message punishes the recipient for
  the sender's mistake and tempts a workaround; redaction kills the payload and
  still delivers the sentence around it. The WARNING in the log is the record.
* FAIL CLOSED. narration_filter is imported defensively on purpose, because a
  missing message-quality nicety is worse than an extra Slack message. This
  module is the opposite: an import failure must not silently turn the gate
  off, so bot.py carries a minimal inline fallback pattern set.
* HIGH-CONFIDENCE PREFIXED FORMATS ONLY. A check that cries wolf trains me to
  skim it, and ten fabricated hits in a row is precisely how a real one gets
  waved through a fortnight later. So: no bare `password:`-style heuristics.
  Every pattern below requires a vendor prefix plus enough trailing entropy
  that prose *about* a secret ("the GOCSPX- secret", "sk-ant- keys") passes
  clean. That property is asserted in the negative half of the test suite.
"""
import re

# (label, compiled pattern). Each requires a vendor prefix AND a long enough
# tail that discussing the format in prose cannot trip it.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("google_oauth_client_secret", re.compile(r"GOCSPX-[A-Za-z0-9_\-]{20,}")),
    ("google_api_key",             re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("anthropic_api_key",          re.compile(r"sk-ant-[A-Za-z0-9_\-]{40,}")),
    ("openai_api_key",             re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{40,}")),
    ("slack_token",                re.compile(r"\bxox[baprse]-[A-Za-z0-9\-]{15,}")),
    ("slack_app_token",            re.compile(r"\bxapp-[0-9]-[A-Za-z0-9\-]{20,}")),
    ("github_token",               re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws_access_key_id",          re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_block",          re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("google_refresh_token",       re.compile(r"\b1//[0-9A-Za-z_\-]{30,}")),
    ("bearer_jwt",                 re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
]


def find_secrets(text: str) -> list[str]:
    """Return the LABELS of credential formats present. Never the values.

    A function that returns the secret it found is a second copy of the leak,
    so this one deliberately cannot be used to print one.
    """
    if not text:
        return []
    return sorted({label for label, pat in PATTERNS if pat.search(text)})


def redact(text: str) -> tuple[str, list[str]]:
    """Replace every live credential with a labelled placeholder.

    Returns (clean_text, labels_found). labels_found is empty on a clean pass,
    which is the only case where the input is returned unchanged.
    """
    if not text:
        return text, []
    found: list[str] = []
    out = text
    for label, pat in PATTERNS:
        out, n = pat.subn(f"[REDACTED:{label}]", out)
        if n:
            found.append(label)
    return out, sorted(set(found))
