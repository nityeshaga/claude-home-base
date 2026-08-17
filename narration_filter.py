"""Procedural-preamble and holding-filler filters for on_text streaming.

Root cause of the recurring "Produce output first" battery ding (flagged
2026-04-25, 05-12, 05-13, 07-19, 07-22, 07-26): bot.py streams *every* text
block to Slack the instant Claude produces it. During a multi-step build each
interstitial "Let me decode the board…", "Let me set up the build script",
"Let me push it to Google Slides" becomes its own Slack message, so a fast,
correct deliverable still lands as a 4-message progress log followed by the
goods. Adding CLAUDE.md text has not fixed it across 6 flags — the reflex fires
mid-turn, when rules loaded at 100% can't gate a habit. This is the structural
gate (per identity.md: "a principle written there is prose, not a gate").

SECOND CLASS, added 2026-08-14: content-free HOLDING FILLER (see
is_content_free_holding). Same interception point, same root cause, opposite
trigger. The preamble filter catches "about to do X"; this catches "still doing
X" — a heartbeat with nothing in it. On 2026-08-13 a 106-applicant screen for
Natalia posted six of these into her DM in 51 seconds ("Waiting on the last 3
batches. Holding." / "Still waiting on batches 6-8. Holding." / "Batches 7 and
8 left. Holding." / "One batch left. Holding." / "Batch 7 is still running." /
"Batch 7 is still researching."), ~12 Slack messages for one request, scored
−0.3. It came immediately after promising her "this is real lookup work, not a
progress log" — so the turn emitted exactly the thing it had just ruled out.

Why prose did not fix it: feedback_status_visibility says "never go silent >2
minutes." That rule was written for BLOCKING runs where no heartbeat is
possible. When work is farmed to background subagents the turn stays live, so
the rule fires with nothing to report and manufactures filler. Amended in the
memory the same day; this is the gate behind the amendment.

Wiring (do this once the homebase/Codex port in bot.py is committed):
    from narration_filter import is_procedural_preamble, is_content_free_holding
    # inside on_text(), after the SKIP / soft-skip checks and BEFORE post_response:
    if first_text_sent and is_procedural_preamble(text_block):
        logger.info(f"Preamble suppressed (not streamed): {text_block.strip()!r}")
        return
    if first_text_sent and is_content_free_holding(text_block):
        logger.info(f"Holding filler suppressed (not streamed): {text_block.strip()!r}")
        return
Note the `first_text_sent` guard: only interstitial blocks are suppressed,
never a first/sole block, so a terse standalone reply is never swallowed.
STILL UNWIRED as of 2026-08-14 — 18 days after this module was written and
tested. An unwired filter is prose with a test suite; the noise it describes
kept landing in the interim. Wiring is 4 lines and needs the bot.py port.

DESIGN NOTES
- Mirrors the existing SOFT_SKIP_PHRASES filter's shape (short + normalized).
- Length cap (<=120 chars) avoids swallowing a real block that happens to open
  with "Let me". A genuine deliverable is essentially never <=120 chars AND
  pure "Let me <verb>" preamble.
- Must NOT swallow the sanctioned status-visibility pattern (up-front
  duration-setting on long opaque runs, per feedback_status_visibility): those
  read "This will take a while…", not "Let me…", so the tight regex threads it.
- Must NOT swallow common sign-offs that start "Let me know …" — explicitly
  excluded and covered by tests.
"""

import re

# Interstitial procedural preamble: present/future statement about what the
# model is *about to do*, not a deliverable. Anchored at start, case-insensitive.
_PREAMBLE_RE = re.compile(
    r"^\s*(?:"
    r"let me(?!\s+know)"                      # "Let me decode…" but NOT "Let me know…"
    r"|now let me"
    r"|alright,?\s+let me"
    r"|ok(?:ay)?,?\s+let me"
    r"|next,?\s+(?:let me|i'?ll)"
    r"|first,?\s+i'?ll"
    r"|i'?ll\s+(?:now|start|go|then|first|next)\b"
    r"|i'?m\s+going\s+to\s+(?:now\s+)?(?:set up|start|build|write|push|run|create|check|pull|grab|decode)"
    r"|let'?s\s+(?:set up|start|build|write|push|run|create|check|pull|grab|decode|do that|get)"
    r")\b",
    re.IGNORECASE,
)

_MAX_PREAMBLE_LEN = 120


def is_procedural_preamble(text_block: str) -> bool:
    """True if `text_block` is a short interstitial 'about-to-do-X' line that
    should be suppressed from Slack rather than streamed as its own message.

    Only the regex + length gate live here; the caller is responsible for the
    position gate (suppress only when it is NOT the first/sole block).
    """
    stripped = text_block.strip()
    if not stripped or len(stripped) > _MAX_PREAMBLE_LEN:
        return False
    # A block with multiple sentences that then delivers content is not pure
    # preamble — only suppress single-clause "Let me X" lines.
    if stripped.count("\n") > 0:
        return False
    return bool(_PREAMBLE_RE.match(stripped))


# --- content-free holding filler ------------------------------------------
#
# The discriminator is NOT "is this short" or "does it say waiting" — it is
# WHAT the block is waiting on. Waiting on my own work units (batches, agents,
# subagent lookups) is my plumbing and carries nothing the reader can act on.
# Waiting on a PERSON, a failure, or an answer is real status and must survive.
# So the internal-unit whitelist below is the whole gate, and anything not on
# it keeps by default — a filter tuned only against noise would start eating
# "waiting on Natalia's approval", which is far worse than one extra message.
_INTERNAL_UNIT = (
    r"(?:batch(?:es)?|agents?|subagents?|jobs?|tasks?|lookups?|runs?|results?|"
    r"searches|search|quer(?:y|ies)|tool calls?|threads?|rows?)"
)

_COUNT = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a few|the last|the final)"
    r"(?:\s+(?:more|additional|other))?"
)

# A qualifier may sit on EITHER side of the count ("the last 3 batches", "the
# remaining 9"). Keeping it as its own token is what lets both orders parse;
# folding it into _COUNT is why "Waiting on the last 3 batches." stopped
# matching once evaluation moved sentence-wise.
_QUAL = r"(?:last|final|remaining|first|next)"
_BARE_COUNT = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a few)"
    r"(?:\s+(?:more|additional|other))?"
)

# Adverbs that front a filler sentence without adding anything: "Just batch 9
# remaining." / "Only batch 9 left." Escaped the 2026-08-14 incident because
# every pattern below was anchored straight at the count or the unit.
_HEDGE = r"(?:just|only|merely|still)\s+"

_HOLDING_RES = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # "Waiting on the last 3 batches." / "Still waiting on batches 6-8."
        # The object may also be a BARE COUNT with the unit elided ("Waiting on
        # the remaining 9.") — but only when the sentence ends there, so
        # "Waiting on the remaining 9 signatures from the client" still keeps.
        rf"^(?:still\s+)?waiting\s+(?:on|for)\s+(?:the\s+)?(?:{_QUAL}\s+)?"
        rf"(?:{_BARE_COUNT}\s+)?(?:{_QUAL}\s+)?"
        rf"(?:{_INTERNAL_UNIT}\b|\d+\s*(?=[.!]*$)).*$",
        # "Batch 7 is still running." / "The lookups are still going." /
        # "Batches 5-9 still researching" — the copula is OPTIONAL; requiring
        # "is/are" is what let the 08-14 form through.
        rf"^(?:the\s+)?{_INTERNAL_UNIT}[\w\s,\-–]{{0,24}}\b(?:(?:is|are)\s+)?still\s+"
        r"(?:running|going|working|researching|processing|in flight)\b.*$",
        # "One batch left." / "Batches 7 and 8 left." / "2 agents remaining." /
        # "Just batch 9 remaining." / "Only batch 9 (rows 224-234) left."
        # The keyword must CLOSE the sentence. With an open `.*$` tail this also
        # matched "Only row 99 is left unverifiable" — a decision, not filler —
        # the same trap `holding off` was already carved out of.
        rf"^(?:{_HEDGE})?(?:{_COUNT}\s+)?{_INTERNAL_UNIT}[\w\s,\-–()]{{0,24}}\b"
        r"(?:left|remaining|to go|outstanding)\s*[.!]*$",
        # "Still running." / "Holding." / "Still holding on the last few."
        # "holding off/out/back on X" is a DECISION, not filler — excluded, and
        # covered by a test ("Holding off on row 99 — unverifiable by name").
        r"^(?:still\s+)?(?:holding(?!\s+(?:off|out|back))|running|going|processing)\b.*$",
        r"^.*\bholding\.?\s*$",
        # Bare progress counters — no verb, no object, pure telemetry:
        # "Still 5 of 10." / "Batch in." / "7 of 10 done."
        # The tail is a CLOSED allowlist, not `[\w\s]*`: an open tail would also
        # swallow "5 of 10 verified against LinkedIn", which is a deliverable.
        r"^(?:still\s+)?\d+\s*(?:of|/)\s*\d+\s*"
        r"(?:done|in|back|complete|completed)?\s*[.!]*$",
        rf"^{_INTERNAL_UNIT}\s+in\s*[.!]*$",
    )
)

# Any of these means the block carries information: a question, a link, a
# failure, a decision, or a human in the loop. Checked FIRST, keeps the block.
_SUBSTANTIVE_RE = re.compile(
    r"\?"                                   # asking them something
    r"|https?://"                           # a link is a deliverable
    r"|\b(?:fail(?:ed|ing|ure)?|error|crash(?:ed)?|timed?\s*out|timeout|stuck|"
    r"retry|retrying|rerun(?:ning)?|blocked|escalat\w*|approval|permission|"
    r"denied|rate.?limit\w*|cap|quota)\b"   # something went wrong
    r"|\b(?:you|your|natalia|nityesh|mike|brooker|ron|ronald|ryan|diana|"
    r"client|his|her|their)\b",             # a person is involved
    re.IGNORECASE,
)

_MAX_HOLDING_LEN = 140


def is_content_free_holding(text_block: str) -> bool:
    """True if `text_block` only reports my own queue state and should not be
    streamed to Slack as its own message.

    Keeps by default. A block survives if it asks a question, carries a link,
    names a failure, or involves a person — see _SUBSTANTIVE_RE. Position gate
    (never the first/sole block) is the caller's job, same as the preamble
    filter.
    """
    stripped = text_block.strip()
    if not stripped or len(stripped) > _MAX_HOLDING_LEN:
        return False
    if stripped.count("\n") > 0:
        return False
    if _SUBSTANTIVE_RE.search(stripped):
        return False
    # Evaluated SENTENCE-WISE, not whole-string. Half the 2026-08-14 incident
    # escaped a whole-string match by stapling two filler sentences together
    # ("Batch in. Waiting on the remaining 9."): neither anchor matched from
    # position 0. A block is content-free only if EVERY sentence in it is, so
    # one real sentence anywhere in the block still keeps the whole thing.
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", stripped) if s.strip()]
    if not sentences:
        return False
    return all(
        any(r.match(s.strip()) for r in _HOLDING_RES) for s in sentences
    )


# --- self-test: run `python3 narration_filter.py` -------------------------
if __name__ == "__main__":
    SUPPRESS = [  # real interstitial narration pulled from battery verdicts
        "Let me decode the board...",
        "Let me set up and write the build script",
        "Let me push it to Google Slides",
        "Now let me render the slide to check it.",
        "Alright, let me pull the transcript first.",
        "Okay, let me set up the deck.",
        "First, I'll grab the source data.",
        "Next, I'll build the shapes.",
        "I'll now start the research job.",
        "I'll go build that as one editable slide.",
        "I'm going to set up the build script.",
        "Let's push it to Google Slides.",
    ]
    KEEP = [  # deliverables / status / sign-offs that must NOT be swallowed
        "Let me know if you want changes.",          # sign-off, not preamble
        "Let me know which option you prefer.",
        "Done — deck's live: https://docs.google.com/x",
        "This will take a while — expect the two links, not a progress log.",
        "Here's the summary you asked for.",
        "Let's go with the second option — it's cleaner and cheaper.",  # a decision, >120? no—must keep via len? it's <120
        "The doubled logo is my pipeline, not a Slides bug.",
        "Yes — but one correction: it was only Tribe AI, no Casper analysis exists.",
        "SKIP",
        "",
    ]
    # The six blocks actually posted into Natalia's DM on 2026-08-13, verbatim
    # from the battery verdict. Any change to the holding filter is measured
    # against the real incident, not against a paraphrase of it.
    HOLD_SUPPRESS = [
        "Waiting on the last 3 batches. Holding.",
        "Still waiting on batches 6-8. Holding.",
        "Batches 7 and 8 left. Holding.",
        "One batch left. Holding.",
        "Batch 7 is still running.",
        "Batch 7 is still researching.",
        # neighbours in the same class, probed rather than assumed
        "Holding.",
        "Still holding.",
        "Waiting on 2 more agents.",
        "Still waiting for the last lookup.",
        "3 agents remaining.",
        "The searches are still going.",
        "Still processing.",
        # The EIGHT blocks posted into Natalia's DM on 2026-08-14, 10:33:55 to
        # 10:34:44, verbatim from the battery verdict (−0.7, the repeat). Added
        # 2026-08-17 because the suite above — written against 08-13 — caught
        # only 4 of these 8. Wiring the filter on the strength of a green suite
        # that had never seen the newer incident would have been a false clean:
        # a gate is only evidence about inputs it has actually been shown.
        "Batch in. Waiting on the remaining 9.",
        "Holding for the remaining batches.",
        "Holding for the remaining 3 batches.",
        "Still 5 of 10. Holding for batches 5-9.",
        "Batches 5-9 still researching (rows 176-234).",
        "Two batches left. Holding.",
        "Only batch 9 (rows 224-234) left. Holding.",
        "Just batch 9 remaining.",
    ]
    HOLD_KEEP = [
        # up-front expectation-setting — the SANCTIONED pattern, must survive
        "This will take a while — expect the two links, not a progress log.",
        "Give me a bit; this is real lookup work, not a progress log.",
        # a person is involved: real status, not plumbing
        "Waiting on Natalia's approval before I send it.",
        "Still waiting on Ron for the July number.",
        "Waiting on your call on whether to include row 77.",
        # something went wrong: always survives
        "Batch 7 failed — rerunning it.",
        "Two agents timed out; retrying those.",
        "Still waiting on the last batch — it's been 6 minutes, may be stuck.",
        # a question always survives
        "Batch 7 is still running — want me to ship the first 100 now?",
        # deliverables
        "Done — 106 rows written to Applications!P10:R115.",
        "50 Yes / 48 Maybe / 8 No. Nine rows flagged low confidence.",
        "Holding off on row 99 — that one is unverifiable by name.",
        "The link is https://docs.google.com/x — still running the tally.",
        "",
        # --- keep-side probes for the 2026-08-17 widenings -------------------
        # Sentence-wise all(): ONE real sentence must save the whole block, or
        # multi-sentence deliverables start disappearing.
        "Two batches left. Row 163 contradicts the sheet.",
        "Just batch 9 remaining. Its rows are all low-confidence.",
        "Done. 119 rows written.",
        # The bare-count class must not eat counts that carry a finding.
        "5 of 10 verified against LinkedIn.",
        "3 of 8 disagree with the sheet.",
        # The hedge prefix must not turn a decision into filler.
        "Only row 99 is left unverifiable.",
    ]
    ok = True
    for t in SUPPRESS:
        if not is_procedural_preamble(t):
            print(f"FAIL (should suppress): {t!r}")
            ok = False
    for t in KEEP:
        if is_procedural_preamble(t):
            print(f"FAIL (should keep):     {t!r}")
            ok = False
    for t in HOLD_SUPPRESS:
        if not is_content_free_holding(t):
            print(f"FAIL (holding, should suppress): {t!r}")
            ok = False
    for t in HOLD_KEEP:
        if is_content_free_holding(t):
            print(f"FAIL (holding, should keep):     {t!r}")
            ok = False
    # Cross-check: neither filter may swallow what the other is meant to keep.
    for t in KEEP + HOLD_KEEP:
        if is_procedural_preamble(t) or is_content_free_holding(t):
            print(f"FAIL (cross-filter swallowed a keeper): {t!r}")
            ok = False
    print(
        f"{len(SUPPRESS)+len(HOLD_SUPPRESS)} suppress / "
        f"{len(KEEP)+len(HOLD_KEEP)} keep cases"
    )
    print("ALL PASS" if ok else "TESTS FAILED")
    raise SystemExit(0 if ok else 1)
