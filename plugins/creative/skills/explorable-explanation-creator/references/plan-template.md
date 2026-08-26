# plan.md — template

`plan.md` is the sign-off surface and the builders' law: nothing built may contradict it. Fill every section; delete the guidance in brackets.

---

# <Title of the explorable>

## Reader

[One paragraph. Who they are, what they want, the tone that fits (ELI5 / curious generalist / practitioner new to this subfield / expert), and what they should be able to do after. Write it like a tutor describing the one student in front of them.]

**Terms they already know / don't know:** [two short lists — a guide, not exhaustive. e.g. for a home cook learning fermentation: knows *yeast, proofing, pH*; doesn't know *lactobacillus, osmotic pressure, brine ratio*. Builders gloss what's on the don't-know side and anything like it; Chad enforces. If the reader is the human asking, confirm with them.]

## Sources

[Either the list of files every fact traces to — or the sentence "No source files; explained from general knowledge," so the human knows which footing this stands on.]

## Tree

[ASCII diagram. Every page, one line of purpose each. Mark doors (→) and cross-links (⇢). Then: node count, max depth.]

```
index — <the crux in one line>
├── 01-<slug> — <purpose>
│   ├── 01a-<slug> — <purpose>
│   └── 01b-<slug> — <purpose>  ⇢ 02a
├── 02-<slug> — <purpose>
│   └── 02a-<slug> — <purpose>
└── 03-<slug> — <purpose> (catalog: table rows are doors)
    ├── …
```

Nodes: N · Depth: D

[Check before presenting: does the front page state a crux and offer a fork, or is it a table of contents? Does any non-catalog page have more than three doors? Does most depth live in one wide fan? Any yes → refactor.]

## Theme

**What the topic literally is:** [the real-world thing this topic already is — the theme plays that completely straight]

**Look:** [palette, type, texture, motion — in a few lines; the rendered index.html is the real spec]

**Metaphor map** — every core concept gets an exact counterpart:

| Concept | In the theme's world |
|---|---|
| | |

**Branch identity:** [how a reader knows which limb they're in — e.g. one accent color per top-level branch]

## Navigation

Breadcrumb · depth indicator · tree map with "you are here" · one consistent hover affordance so what's clickable is never a guess. [Describe how these look in this theme.]

## Pages

[One block per page, including index. This is what each builder receives.]

### `<file>.html` — <title>
- **Purpose:** [the 80/20 of this subtree in one sentence]
- **Reading level note:** [only if it differs from the reader paragraph]
- **Visual / mechanic:** [name the mechanic from mechanics.md, or describe the diagram; what the default state shows, what interaction adds]
- **Doors:** [→ file — the element that is the door (slice, box, row, word). Label = the words the reader is curious about, never a section number or title]
- **Cross-links:** [⇢ file — if any]
- **Facts to carry:** [numbers, quotes, claims this page must state, with source file if sourced]

## Writing style

Crux first. Plain prose; one-line gloss on any term of art. Numbers never paraphrased. Theme in the chrome, not the sentences. [Add anything specific to this reader.]

## Delight

[Two or three dry, quiet easter eggs. Optional.]

## Build notes

Shared assets: `theme.css`, `nav.js` (builders copy the index's structure and never edit these). Budget: responsive; must fit a 1366×700 viewport (a browser window on a 13-inch laptop) without scroll as the floor, and the prose column is no taller than the visual. Larger windows get used gracefully, not letterboxed. Mobile: single column, nothing important hidden. Tree map opens on demand (button or key), never a permanent sidebar. Vanilla JS only, no build step, no network dependencies.
