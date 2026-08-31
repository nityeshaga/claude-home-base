# Spec Templates

The documents produced before pages are built. Keep them short — they are working notes for
one author and inputs to reviewers and builders, not deliverables.

## Contents

1. `persona.md`
2. `question.md`
3. `storyboard.md` + `shared/map.js`
4. X-factor entries (added to the cards)
5. `design-plan.md`

---

## 1. persona.md

The persona is what lets a reviewer check "reading level" against something concrete.

```markdown
# Reader persona

**Who they are.** One paragraph: what they do, why they came to this page, how much
patience they have, what device they're on. Which of Strogatz's three audiences they are
(traumatized / perplexed / natural) and what that means for tone.

**What they want.** One or two sentences, in their words.

**Tone that fits.** A few adjectives; what would feel patronizing and what would feel cold
to this reader.

**Afterwards they should be able to…** 2–4 concrete things: explain X to a colleague, read
Y and say Z, make decision W. These define where the spine ends.

**What they probably believe that's wrong.** 2–3 items. These are the reversals the
explanation will deliver.

**Terms they already know.** A handful. The first page should need nothing beyond these.

**Terms they don't know yet.** A handful. These are part of what they are here to learn —
introduce them, name them, connect them to something they know. The list is a guide for
reviewers, not a quota for pages.
```

Produce it in a short dialogue with the user (3–5 questions), draft, show, get sign-off.
If the user says "you decide," choose the perplexed adult non-specialist and say so.

## 2. question.md

Written by the orchestrator. Generate three candidates — Case's three hook forms: the
blatant question, the story, the game — judge them against the persona (would a bored
version of this reader still click? does page 1 need only known terms?), pick one.

```markdown
# Central question

**The question.** One sentence the persona would actually ask.
**Why they'd care.** One sentence, in their terms.
**Hook.** A one-paragraph sketch of page 1: what they see, what they already recognize,
what pulls them to page 2. Needs nothing beyond the persona's known terms.
**Candidates considered.** The other hooks, two lines each, and why this one won.
```

## 3. storyboard.md

One card per page. This is a teaching plan, written by the orchestrator as a teacher. It
describes what each page *explains* and how the pages connect; it does not decide visuals
(that's §4).

```markdown
## [id] — [Title as the reader sees it]
- **parent:** [id]  **children:** [ids] · or leaf — then: how the page closes
- **how it follows from the parent:** one line (continues it? overturns it?)
- **idea:** the single thing this page explains
- **how it's explained:** teaching notes — the concrete example or analogy, the reversal if
  there is one (what the reader expected vs. what's true), the connection to something they
  already know, the terms named here
- **afterwards the reader can say:** one sentence in their voice
- **ways forward:** how the child page(s) are offered, as the reader sees them — a question
  or a destination; for a fork, the choice as the reader would feel it
- **wants a visual of:** optional, a phrase — decided properly in §4
```

Alongside the cards, write `shared/map.js` — the machine-readable half. One line per page:

```js
id: { title: "As the reader sees it", file: "pages/<slug>.html", children: ["nextId"] }
```

Add a field only when it's true of that page: `gate: "soft"|"hard"` (a playable the reader
should use before moving on), `sandbox: true`, `rejoin: "id"` (a leaf offering a way back),
`new_terms: [...]` (terms from the persona's "don't know yet" list first named here). A fork
is simply a page with two or more children — nothing to declare. Top level: `title`, `slug`,
`root`, `spine_end`, `defaults`.

Then run `python scripts/validate_tree.py <project> --no-files`. It prints the tree as an
outline with a one-line summary (pages, spine length, depth, forks, gated pages, leaves) —
look at that shape and ask whether it matches the explanation you have in mind. It also
catches orphans, cycles, dead links and a fork on the root.

## 4. X-factor entries

After the storyboard is reviewed, add to each card:

```markdown
- **x-factor:** diagram | chart | annotated screenshot | photo | video | animation | playable
- **spec:** what it shows, what's labeled, what data (and source) if any, the one thing a
  reader should notice. Enough for a builder who has the card and the design plan.
```

For a **playable**, the spec is Case's message→mechanics exercise for *this page or
cluster* (design-patterns.md §1): the cause→effect the reader should discover; the few
rules whose play produces it; what's visible; what the reader can change; the counter-
intuitive result; where the model lies. If several playables share one system, write the
spec once and reference it; they share `shared/model.js`. Note the gate (design-patterns
§3) only for playables where proceeding without doing the thing would defeat the page.

## 5. design-plan.md

Produced once by the design planner so every builder uses the same identity. Read the
`frontend-design` skill if installed; the design should belong to this subject, not to a
template.

```markdown
# Design plan
**Subject world.** What the topic looks like — materials, instruments, places — and the
one aesthetic risk we're taking.
**Palette.** 4–6 named hex values with roles (ground, ink, accent, accent-2, warn, muted);
color-blind safe for any meaning-carrying pair.
**Type.** Display, body, utility faces with clamp() ranges (16px floor).
**Layout.** Desktop text/stage ratio (`--ex-text-col`); mobile stacking order (heading and
first paragraph before the visual).
**Signature.** One memorable element reused on every page.
**Visual language.** How diagrams are drawn (stroke, fill, labels), how charts look, how
screenshots are framed — so a dozen parallel builders produce one family of figures.
**Wayfinding chrome.** The minimap's node glyphs per state, edge style, orientation, map
button label; any restyling of the top bar.
**Motion.** What animates and what never does; reduced-motion behaviour.
**Voice.** Three sample lines in the persona's tone, and two that would be wrong.
```
