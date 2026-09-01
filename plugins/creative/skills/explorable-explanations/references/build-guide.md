# Build Guide

How a finished explorable is laid out on disk, what a page is, and what every page must
satisfy. The orchestrator writes the prose and builds most pages; playable builders fill the
stage on the few pages that have one. Both read this.

## Contents

1. Project layout
2. `shared/map.js` — the tree
3. The runtime (`shared/explorable.js`) — what you get for free
4. The page: structure, viewport, budget
5. Writing the prose (orchestrator)
6. Building a visual (visual builders)
7. Building a playable (playable builders)
8. Design tokens and consistency
9. Accessibility and motion
10. QA

---

## 1. Project layout

```
<project>/
├── persona.md  question.md  storyboard.md  design-plan.md
├── index.html                      root (hook) page
├── pages/<slug>.html               one file per page
├── shared/
│   ├── map.js                      window.EXPLORABLE_MAP — the tree
│   ├── explorable.js               runtime (don't edit; copy from template)
│   ├── explorable.css              structural base (don't edit; copy from template)
│   ├── theme.css  theme.js         identity, from design-plan.md
│   └── model.js                    only if playables share a system
├── assets/                         images, screenshots, fonts, data files
├── review/                         reviewer findings per round, CHANGELOG.md
└── _screens/                       output of scripts/check_pages.py
```

Every page loads `shared/explorable.css`, `shared/theme.css`, then `shared/map.js`,
`shared/theme.js`, `shared/explorable.js` (and `shared/model.js` if it exists), then its
own inline script if it has one. Classic scripts and relative paths, so `index.html` opens
by double-click with no server.

## 2. `shared/map.js`

The machine-readable half of the storyboard. Per page: `{ title, file, children }`, plus
`gate`, `sandbox`, `rejoin` or `new_terms` only where they apply. A page with two or more
children *is* a fork. See the comment block in the template and `specs.md` §3.

## 3. The runtime

`shared/explorable.js` adds to every page, from `map.js` and stored state: the breadcrumb,
the minimap (press `m`), position words ("6 / 14", "side path · rejoins at…"), fork memory
on return, the deep-link hint, keyboard shortcuts, and forward-link handling. Write forward
links as `<a data-ex-link="childId">…</a>`; the runtime wires them and carries state.

API, for pages that need it (mostly playables):

```js
EX.get(key, default) / EX.set(key, value)   // reader state, persisted + in the URL hash
EX.gate.open() / EX.gate.fail()              // for soft/hard gates on playable pages
EX.link(id, text)                            // an <a> you can place inside the stage
EX.on('ready'|'gate-open'|'hatch', fn)
EX.prefersReducedMotion
```

## 4. The page

**Structure.** `<body data-page="id">`; one `<main class="ex-page">` with a `<section
class="ex-text">` (heading, prose, and an `.ex-next` block of ways forward) and a
`<section class="ex-stage">` (the visual). Title: "Page title — Explorable title".

**Viewport.** At 1440×900 and larger, no vertical scroll. At 390×844 the sections stack —
heading and first paragraph first, then the visual, then the rest — and the page may scroll;
no horizontal scroll.

Each visual has to be *legible* at 390px, not merely fit: a figure that only shrinks becomes
unreadable, so give it a narrow layout of its own. Text inside a figure follows the same
floor as body text — a label that needs to go under ~12px means the figure needs
restructuring, not smaller type.

**Length.** However much prose the idea needs, within the viewport — in practice a couple
of short paragraphs beside a visual. If it won't fit, split it: sometimes into two ideas,
more often into two pages that both serve the same idea.

**The visual** is whatever the x-factor pass chose: an SVG, an `<img>`, a `<figure>` with a
caption, a `<video>`, a canvas, or a playable. It lives in `.ex-stage`, scales to the box,
and has an `aria-label` or caption that says what it shows.

## 5. Writing the prose

One author, one pass, from the storyboard. Each page picks up where the previous one left
off, explains its idea in the persona's voice, names and defines the terms it introduces in
the reader's own terms, and ends by offering the ways forward (the `.ex-next` block) saying
where each leads. Leaves close properly (tree-design §2).

Two things worth watching. Where a page has a reveal — a bet, a result the reader produces
— write the sentence that states the claim in words *after* they've seen it; the visual is
the evidence, the prose is the point. And where a visual or playable simplifies the real
thing, say so plainly on the page rather than in a tooltip.

The test: with every visual removed, the pages should still read as a connected account of
the topic.

## 6. Building a visual

Into `.ex-stage`, from the card's x-factor entry:

- Use the design plan's visual language and tokens (`var(--ex-*)`), never literal colors.
- Make the one thing the reader should notice the most visually prominent thing; label what
  carries the argument and leave the rest quiet.
- Real data: put the source in a caption. Screenshots: frame per the design plan; redact
  anything private.
- Static is fine. A small autoplaying animation suits an idea that's about change over time;
  respect `prefers-reduced-motion` by showing the end state.
- If the figure makes a sentence wrong or redundant, fix the sentence — you wrote it.

## 7. Building a playable

Inputs: the card and its playable spec (design-patterns.md §2), the page file with prose in
place, `design-plan.md`, this guide, and `shared/model.js` if the spec says the model is
shared. Then:

- Keep the rules (model) separate from the drawing; a `redraw()` you can call after any
  change. If the model is shared, it lives in `shared/model.js` and is pure logic.
- Hand-author the starting state so the first interaction is rewarding. Direct
  manipulation: act on the thing itself. Respond generously and immediately.
- Implement the gate the spec names, if any. Soft: `EX.gate.open()` on commit or first
  touch. Hard: `EX.gate.open()` when solved, `EX.gate.fail()` on a wrong attempt; the
  runtime shows "Show me how" after three — wire `EX.on('hatch', …)` to demonstrate.
- Store what the reader changes with `EX.set` so it carries to later pages that share the
  model, and so the URL reproduces what they saw (use a seeded PRNG, not `Math.random`).
- Keyboard equivalents for every pointer action; visible focus; reduced-motion makes steps
  discrete.
- Say on the page, or make sure the prose says, where the model simplifies the real thing.

## 8. Design tokens and consistency

All identity is in `shared/theme.css` (overrides of the `--ex-*` custom properties plus any
restyling of the stable chrome classes `.ex-chrome`, `.ex-crumbs`, `.ex-map-toggle`,
`.ex-map`, `.ex-mm-*`) and `shared/theme.js` (optional hooks that draw the minimap's node
glyphs, edges, orientation and button label — see the header of the minimap section in
`explorable.js`). The design planner produces both from `design-plan.md`. Builders use the
tokens; a palette change is then one file. Meaning-carrying color pairs must survive
color-vision deficiency — add a shape or label difference too. Body text never below 16px.

## 9. Accessibility and motion

Every visual has an `aria-label` or caption. Every control is keyboard-operable with
visible focus. `prefers-reduced-motion` is respected. Nothing essential is hover-only. Tap
targets ≥ 44px on mobile.

## 10. QA

```
python scripts/validate_tree.py <project>   # structure, links, rough reading-level check
python scripts/check_pages.py  <project>    # viewport, errors, screenshots
```
Then open both screenshots of each page and ask: does the page explain its idea in words;
does the visual show the thing the words are about; can the reader see at a glance where
they can go next and what they'll find there.
