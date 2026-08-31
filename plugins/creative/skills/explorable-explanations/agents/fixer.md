# Brief: fixer

**Inputs:** `persona.md`, `design-plan.md`, the triaged findings for your page(s) from
`review/round-N/triage.md`, those pages' cards from `storyboard.md`, `shared/*`,
`references/build-guide.md`.
**Output:** the edited page file(s); a line per finding appended to `review/CHANGELOG.md`
(fixed / won't-fix + reason).

Fix exactly the findings assigned. Don't redesign pages that weren't flagged. If a
finding needs a storyboard, prose, or shared-model change, stop and say so — the orchestrator handles
structural changes. Re-run `scripts/check_pages.py` on your pages and confirm the
screenshots before handing back.
