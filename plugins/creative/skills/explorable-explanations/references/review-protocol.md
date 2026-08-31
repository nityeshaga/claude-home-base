# Review Protocol

Case's hard-won lesson is the 90% crap rule: most of the work is discarding what didn't
survive playtesting. This skill can't watch a human read the explorable, so it simulates
the specific failures playtesting reveals, using **independent, clean-slate reviewers**.
Independence is the whole point — a reviewer who has seen the author's reasoning grades
the intent, not the experience.

## Contents

1. Independence rules
2. The reviewer roster
3. When reviews happen (three checkpoints)
4. Findings format
5. Triage and the fix loop
6. Exit criteria

---

## 1. Independence rules

- Each reviewer is a **separate subagent** with a fresh context.
- A reviewer receives **only**: `persona.md`, its brief from `agents/`, and the artifact
  under review (the storyboard, or the built project folder). Never `question.md`,
  `design-plan.md`, the orchestrator's notes, or other reviewers' findings. (Exception: the
  SME adversary also gets any playable specs, because its job is to audit the model's
  honesty.)
- Reviewers write findings to `review/round-N/<role>.md` and do not edit the project.
- Never spawn a reviewer with instructions like "check that it's good." Each role has a
  narrow lens and a fixed set of questions; that is what makes the findings actionable.
- If subagents are unavailable (plain Claude.ai), run each role sequentially *after*
  writing its brief to a file, answer it as literally as possible from the artifact alone,
  and mark the round "degraded independence" in the findings header. It's better than no
  review, and the human's own review compensates.

## 2. The reviewer roster

| Role | Brief | Lens | Simulates |
|---|---|---|---|
| **Playtester-as-persona** | `agents/reviewer-playtester.md` | Walks the tree *as the persona*, knowing only the known terms; narrates confusion, boredom, delight, and where they'd quit | The actual reader |
| **Skimmer** | `agents/reviewer-skimmer.md` | Reads only headings, link texts and visuals; reports what they believe the explorable says | Earth Primer's skimming readers; tests gating |
| **Interaction auditor** | `agents/reviewer-interaction.md` | Case's seven Neurons rules + Magic Ink; every widget, every link | Crap-interaction, dead clicks, indirect manipulation, over-explanation |
| **Wayfinding auditor** | `agents/reviewer-wayfinding.md` | Tree shape, forks, minimap, breadcrumb, deep links, dead ends, sibling-branch leakage | Getting lost |
| **Subject-matter adversary** | `agents/reviewer-sme.md` | Is the model *true enough*? Where does the simplification teach something false? Are limitations stated? Can the sandbox break the argument? | Victor's skeptical active reader |
| **Static reader** | `agents/reviewer-static.md` | Reads every page with scripts disabled (prose + frozen stage) and checks the explanation still holds | Victor's "works as static text" rule; also screen-reader users |

Run all six at the build checkpoints. At the storyboard checkpoint run playtester,
wayfinding and SME (there's nothing to click yet).

The roles and briefs are unchanged from the first version of this skill and will be revised
separately once the prose-first pipeline has been run; the known gap is that no role yet
asks "what did the reader learn on this page, and where did the page say it."


## 3. Checkpoints

**Checkpoint B — storyboard.** Playtester, wayfinding, SME, on `storyboard.md` +
`shared/map.js` (and, once the x-factor pass is done, on any playable specs — the SME checks
that the rules really produce the claimed result). Cards are cheap to change; HTML is not.
Do not start building until B has no Blocker findings.

**Checkpoint C — built spine.** All six roles on the spine pages only, if the branches
aren't built yet. Fix first, so the branch pages are built against a corrected spine.

**Checkpoint D — full tree.** All six roles on everything. Then a second, shorter round
after fixes, re-running the playtester plus the roles whose findings were addressed. Two
rounds at D is the usual minimum; when in doubt, run another.

## 4. Findings format

Every finding, one per bullet, in the reviewer's file:

```
- [SEVERITY] page-id · location — what happens · why it matters for the persona · suggested fix
```

Severities:
- **Blocker** — the persona would quit, learn something false, or be unable to proceed
  (broken gate, unknown term with no introduction, dead end, unreadable on mobile).
- **Major** — the idea on this page doesn't land (crap-interaction, over-explanation,
  twist revealed before the bet, static read incoherent, lost in the tree).
- **Minor** — friction (tone slip, link text vague, juice missing, focus ring missing).
- **Praise** — one or two things that work, so fixes don't break them.

Reviewers end with a three-line summary: *would the persona finish the spine? would they
be able to do the "afterwards" items? what is the single most important fix?*

## 5. Triage and the fix loop

The orchestrator (never the reviewers) triages:

1. Merge all findings; de-duplicate; keep severities (when reviewers disagree, keep the
   higher).
2. Group by page. Most fixes you make yourself, since you wrote the pages; spawn
   `agents/fixer.md` when there's a batch large enough to be worth parallelising, giving it
   the findings for its pages and only those pages' cards.
3. Findings that implicate the **storyboard** (wrong order, missing page, fork that
   shouldn't exist) are fixed in the storyboard first, then map.js, then pages. Don't
   patch around a structural problem in copy.
4. Findings that implicate the **prose** go back to the orchestrator (one author); findings
   that implicate a shared **model** go to its playable builder, then every page using it is
   rechecked by `check_pages.py`.
5. After fixes, re-run the scripts, then the next review round.

Keep a `review/CHANGELOG.md`: round, finding, decision (fixed / won't-fix + reason).
Won't-fix needs a reason the user would accept.

## 6. Exit criteria

Deliver when all are true:
- `validate_tree.py` and `check_pages.py` pass with 0 FAIL, and every WARN is either fixed
  or listed with a reason in the changelog.
- Last review round: no Blockers, and no Majors left on the spine. Anything still open is
  listed for the user with a reason.
- Playtester's last summary says the persona would finish the spine and can do the
  "afterwards" items.
- Every page's screenshot (desktop + mobile) has been looked at by the orchestrator.
- Any playable exposes the parameters the SME adversary named as load-bearing.
