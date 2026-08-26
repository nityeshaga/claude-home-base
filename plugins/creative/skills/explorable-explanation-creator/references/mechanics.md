# Mechanics — the interactive vocabulary

An explorable mechanic is a small piece of JavaScript that lets the reader *do* something to an idea and watch it respond. It earns its place on a page when the idea has a parameter — something that varies, and whose variation is the point. A mechanic that decorates rather than teaches is noise; a diagram would have been better.

Three rules that hold for every mechanic:

- **The default state already explains the page.** A reader who never touches anything still gets the 80/20. Interaction deepens; it never unlocks.
- **One mechanic per page, usually.** Two competing interactions on one screen split attention. If a page wants two, it probably wants to be two pages.
- **Vanilla JS, inline or in one shared `nav.js`, no build step, no CDN.** The folder must open from disk, offline, years from now. SVG and Canvas are both fine; prefer SVG when parts need to be doors.

Touch and keyboard must both work (sliders: `<input type=range>` gets this free; custom drag handlers need pointer events).

## For inspiration, not a menu

This list is a starting point, not a catalogue to pick from. Use it two ways: take an item straight when it fits, or read it to broaden your sense of what a page can do and invent something the list doesn't have. A mechanic nobody has built before is allowed; a page that picked #4 because #4 was on the list is not the point.

| # | Mechanic | Use when | Gist |
|---|---|---|---|
| 1 | **Slider-driven diagram** | One quantity drives a shape, a curve, a count | `<input type=range>` → redraw SVG on `input`; label shows the live value |
| 2 | **Draggable number in prose** (Tangle-style) | A sentence contains a number the reader should question | `<span class=tangle>` scrubbed by pointer drag; dependent numbers in the paragraph recompute |
| 3 | **Step-through simulation** | A process unfolds in steps and the order is the lesson | Play / pause / step buttons; state rendered each tick; a scrubber to jump |
| 4 | **Toggle comparison** | Two states of the same thing: before/after, with/without, A/B | A single switch swaps both the visual and the one-line caption |
| 5 | **Guess-then-reveal** | The reader has an intuition and it's probably wrong | Reader sets a guess (slider, click on a chart); reveal overlays the truth; the gap is the lesson |
| 6 | **Build-up sequence** | A diagram is only clear if assembled layer by layer | "Next" adds one layer; each layer gets its caption; last state is the full diagram |
| 7 | **Hover-to-annotate** | A dense diagram needs labels but labels would clutter it | Hovering (or tapping) a part shows its note; nothing moves |
| 8 | **Clickable regions as doors** | The visual is a map of the layer below | SVG groups with `<a href>`; hover affordance identical to text links |
| 9 | **Live sandbox** | The idea is an input→output transform (a regex, a formula, a prompt) | A small editable input; output recomputes on every keystroke; a few preset examples |
| 10 | **Scrub timeline** | Something changes over time and the shape of the change matters | Drag across a time axis; the visual re-renders for that moment |
| 11 | **Counterfactual knob** | "What if X were different?" is the real question | A control for X with a clearly marked "actual" position; the visual answers |
| 12 | **Sortable / filterable catalog** | A wide fan whose rows are doors | Table with column-sort and one filter; every row a link |
| 13 | **3D scene** (three.js, vendored) | The idea is spatial or structural — a molecule, an architecture, a network, three dimensions of data | Orbit/zoom a scene whose default camera angle already explains it; hover or click parts for labels or doors. Ship `three.min.js` inside the folder so the no-network rule still holds; this is the heavy option, so the page must earn it |

Combine freely but not carelessly: a slider whose diagram's parts are also doors (1 + 8) is the format's signature move — the control teaches this layer, the parts lead to the next. Stick figures are fun.

## Choosing

Read the page's purpose sentence from `plan.md` and ask: *what would the reader most want to poke at here?* If the answer is "nothing, they want to see the shape of it" → a diagram, no mechanic. If the answer names a quantity → 1, 2, 10, 11. A process → 3, 6. A belief → 5. A comparison → 4. A collection → 8, 12. Something spatial → 13. Something none of these fit → invent it, and hold it to the same three rules above.

## Quality bar

Before a builder calls a mechanic done, it drives it in a real browser: the control moves, the visual responds, the default state reads correctly with the page fresh, and nothing pushes the page past one viewport at 1366×700, and the prose beside it is no taller than it.
