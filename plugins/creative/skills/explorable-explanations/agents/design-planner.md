# Brief: design planner

**First action, before reading anything else or writing a line of the plan: load the
`frontend-design` skill.** Invoke it if your environment exposes skills as tools; otherwise
read its SKILL.md — on Claude.ai at `/mnt/skills/public/frontend-design/SKILL.md`, in Claude
Code under `~/.claude/skills/` or the project's `.claude/skills/`. Search for it before
concluding it isn't there. It exists to stop you producing the handful of looks that every
model reaches for by default, and a plan written without it will almost certainly be one of
them. If you truly cannot find it, say so in the first line of `design-plan.md` and proceed
from `references/specs.md` §5 — don't silently skip it.

**Other inputs:** `persona.md`, `question.md`, `storyboard.md` (skim: what kinds of visuals
the cards ask for), `references/specs.md` §5, `assets/template/shared/explorable.css` (read
the `:root` tokens — you override these), `assets/template/shared/theme.js` (the minimap hook
stub) and the hook docs at the top of `assets/template/shared/explorable.js`'s minimap
section.
**Output:** `design-plan.md` (stating in a header line which design guidance it was written
against), `shared/theme.css`, and `shared/theme.js` (minimap hooks).

Work in the two passes that skill describes: draft the direction, then critique your own
draft — would I have produced this for any similar brief? does it match one of the default
looks the skill names? — and redo it if the answer is yes. Ground the identity in the
subject's own world (what the topic's things look like, what the persona's world looks
like), not in a template. Then:
- Palette as `--ex-*` overrides; check the accent/ink and any two meaning-carrying colors
  for color-vision-deficiency contrast. Provide a second encoding (shape/label) in the
  plan for anything color means.
- Type as `--ex-font-*` with self-hostable or system fallbacks; sizes as clamp() ranges
  with a 16px floor.
- Layout: the two-column desktop grid ratio (`--ex-text-col`) given the visuals the cards
  call for; on mobile, heading and first paragraph before the visual.
- Visual language: how diagrams are drawn, how charts look, how screenshots are framed, so
  many parallel builders produce one family of figures.
- Signature element: one, reusable on every page, cheap to draw in SVG.
- Wayfinding chrome: design the minimap as part of the identity — glyphs for each node state
  that come from the subject's world (cars, cells, coins…), edge style, orientation, map
  button label. Implement in `shared/theme.js` (hooks) + `shared/theme.css` (selectors
  `.ex-mm-node.visited/.current/.locked/.fork/.sandbox`, `.ex-chrome`, `.ex-map-toggle`).
  Then open `index.html`, press `m`, and screenshot it at 1440×900 and 390×844: every node
  state must be distinguishable, labels must not collide, the current page must be obvious.
- Voice: three sample narrator lines in the persona's tone (from persona.md), plus two
  lines that would be *wrong* for this persona and why.
