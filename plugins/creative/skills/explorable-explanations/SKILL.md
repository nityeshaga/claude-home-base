---
name: explorable-explanations
description: Build an explorable explanation — a tree of short, visual, single-viewport web pages (HTML+CSS+JS) that explains a topic one idea per page, where depth is expressed as navigation rather than scrolling, in the tradition of Nicky Case and Bret Victor. Use this whenever the user wants to explain, teach, or make someone understand a concept, system, piece of research, framework, or argument as a set of interlinked pages instead of one long scrolling page; says "explorable", "explorable explanation", "interactive explainer", "learn by playing", "playable essay", "Nicky Case style", "Parable of the Polygons style", or "like Bret Victor"; or asks for a website/one-pager that teaches something and would benefit from being split into a tree. Also use it to turn an existing article, paper, lecture, or mental model into something a reader can navigate at their own depth. Uses subagents where they pay off (a visual advisor, a builder per playable, independent clean-slate reviewers).
---

# Explorable Explanations

When someone asks for a beautiful HTML page that explains a piece of research, the result
is one long scroll: everything the topic has to say, stacked, and the reader scrolls
through all of it whether they care or not. An explorable explanation is the levelled-up
alternative. The same explanation is split into a **tree of short pages**, each fitting one
laptop viewport and carrying one idea, where every page is one step deeper into the rabbit
hole than the page above it. The reader chooses which rabbit holes to follow. Depth is
navigation, not scrolling.

A page is, by default, what a page in a good explanatory article is: a short piece of prose
and one visual that earns its place — a diagram, a chart, an annotated screenshot, an
image, a short video. Some pages will carry a **playable** — something the reader operates
rather than looks at — but only where operating a system teaches what a picture can't.
Case and Victor both warn against interaction for its own sake; in practice most pages
don't need it, and a tree of impressive widgets with no teaching between them is worse than
a plain article. The explanation comes first; everything else serves it.

Read `references/playbook.md` once before your first project. It is the *why* behind this
skill — Case's arc, Victor's ladder, Strogatz's empathy — and you'll apply it with better
judgment than any checklist here.

## Roles

You, the orchestrator, are the **teacher and the author**. You own the persona, the central
question, the storyboard, the prose, and the building of the pages — one author holding the
whole argument is what makes the tree read as one piece. Subagents do the few things that
genuinely benefit from a separate context:

- **Design planner** — one, producing the visual identity you build against.
- **Visual advisor** — one, after the x-factor pass: suggests stronger figures and playables
  worth building. It advises; you decide.
- **Playable builders** — one per playable (or shared-model cluster). A playable needs a
  small system held in focus and iterated on, which is worth its own context.
- **Reviewers** — independent, clean-slate, per `references/review-protocol.md`.

Everything else — the storyboard, the prose, the ordinary visuals, the assembly — you do
yourself. It's faster and the pages come out connected, which is the thing that matters most.

Briefs are in `agents/`; `agents/README.md` has the spawning pattern. If subagents are
unavailable, run the roles sequentially from their briefs and say so.

## Workflow

Project folder: `<name>-explorable/` (layout in `references/build-guide.md` §2). Keep
`PLAN.md` at the root with these steps as a checklist.

### 1. Persona — with the user, briefly

`references/specs.md` §1. A few questions: who is this for, what should they be able to do
or explain afterwards, how much ground should it cover and how deep may it go, tone, what
they already know. Draft
`persona.md`, get sign-off. The known/unknown term lists are a reading-level guide that
reviewers can check against; they are not a quota.

### 2. Central question

Come up with three candidate questions yourself — a blatant one, a story, a game or puzzle
— each with a one-paragraph sketch of page 1. Pick the one this reader would actually
want answered, whose first page needs nothing they don't already know. Write `question.md`
(specs §2) with the runners-up noted. Show the user; continue unless they object.

### 3. Storyboard — teaching mode

This is the step that decides whether the explorable teaches. Read
`references/tree-design.md`, then think as a teacher, not a widget designer: starting from
the central question, what must the reader understand first? What do they already believe
that is wrong, and where is the reversal that corrects it? What follows from what, and what
overturns what — Case's THEREFORE/BUT is a good way to feel out the spine of the argument.
Where does the reader's interest genuinely fork ("I care about X" vs "I care about Y"), and where is a deeper rabbit hole an
optional side path? Where does it end, and what should the reader be able to say or do at
that point?

New questions can open as you go deeper — a page often exists because its parent raised
something it didn't answer, and a fork is two questions the reader chooses between. Make
the reader want each one before you answer it. Every question you open is either answered
somewhere in the tree or deliberately left as theirs to explore.

Write `storyboard.md` — one card per page (specs §3): the idea, what the page explains and
how, the reversal if there is one, the sentence the reader could say afterwards, and what
the page offers as the way(s) forward. Write `shared/map.js` to match. Run
`python scripts/validate_tree.py <project> --no-files`.

Don't decide visuals yet. A card may say "this idea wants a picture of…" but the storyboard
is about the explanation.

**Checkpoint B** (review-protocol.md §3): spawn the storyboard reviewers. Cards are cheap to
change; fix the argument here, not in HTML.

### 4. X-factor pass — what carries each page

Read `references/design-patterns.md` — it matches kinds of ideas to kinds of media
(diagram, chart, annotated screenshot, photo, video, animation, place-your-bets reveal,
playable) and has the playable patterns and craft notes. Then go card by card and choose
the right medium for that page's idea.

When a page gets a playable, that's where the message→mechanics exercise applies, to that
page or cluster, producing a short spec (design-patterns §2). Playables sharing one system
share one model. Record each decision on the card (specs §4).

Then spawn `agents/visual-advisor.md` on the storyboard. It suggests stronger figures,
better media, playables worth building, and things to cut. It advises; you decide — adopt
what improves the explanation and drop the rest, then update the cards.

### 5. Build

1. Copy `assets/template/*` into the project. `shared/explorable.js` and
   `shared/explorable.css` are the runtime (tree navigation, minimap, state, forward
   links) — don't edit them; identity goes in `shared/theme.css` / `shared/theme.js`.
2. Spawn `agents/design-planner.md` → `design-plan.md`, `theme.css`, `theme.js`. Its brief
   starts by loading the `frontend-design` skill; check the plan says which guidance it was
   written against before you build from it.
3. **Build the pages yourself**, in one pass, from the storyboard: the prose in the
   persona's voice with the connective tissue that makes the tree read as one argument, and
   the visual on each page. You designed the tree and you're holding the whole argument —
   that's what keeps the pages connected, and it's faster than briefing builders.
4. Spawn `agents/playable-builder.md` for each playable (or each shared-model cluster).
   It gets the card, the spec, the design plan, the page file with the prose already in it,
   and the build guide. It fills the stage; it doesn't rewrite the prose, though it may flag
   a sentence that no longer matches.
5. Run `scripts/validate_tree.py` and `scripts/check_pages.py`. Look at every screenshot,
   desktop and mobile.
6. **Checkpoints C and D** per `references/review-protocol.md`, with fixers per page.

### 6. Deliver

The project folder (opens from `index.html`, or `python -m http.server`), a one-paragraph
tour with the minimap screenshot, the persona, and `review/CHANGELOG.md`. Every page URL
carries reader state, so mid-tree links are shareable.

## Principles to keep in view

- **The explanation must stand on its own.** If the visuals were removed, the pages should
  still read as a clear, connected account of the topic. Visuals deepen; prose explains.
- **Love the question first, end with the reader's own.** Hook needs no prior knowledge;
  each page picks up where its parent left off; every path ends with a proper close.
- **One idea per viewport.** If it doesn't fit, it's two ideas or it's the wrong medium.
- **Interaction where it earns its place.** A playable when operating the thing is the
  lesson; otherwise the visual that shows it best.
- **Depth is navigation.** The ways forward from a page are obvious and say where they
  lead; side paths are labeled; the reader can always see where they are.
- **Honest about the model.** Where a simplification or a playable's rules diverge from the
  real thing, the page says so plainly.
- **Write for the persona.** Vocabulary is part of what they're learning; name things,
  define them in the reader's terms, connect them to what they already know.

## Reference map

| Need | Read |
|---|---|
| Why (Case, Victor, Strogatz distilled) | `references/playbook.md` |
| Designing the tree: spine, forks, side paths, wayfinding, links | `references/tree-design.md` |
| Choosing a visual or playable for a page; playable patterns | `references/design-patterns.md` |
| Templates: persona, question, storyboard card, x-factor spec, design plan | `references/specs.md` |
| File layout, runtime API, page contract | `references/build-guide.md` |
| Reviewer roles, rounds, findings, triage, exit | `references/review-protocol.md` |
| Subagent briefs | `agents/*.md` |
| Starting files (runtime, CSS, templates) | `assets/template/` |
| Structure + reading-level check | `scripts/validate_tree.py <project>` |
| Viewport / error / screenshot checks (Playwright, install once) | `scripts/check_pages.py <project>` |

## Lessons from the first real run

Recorded as observations, not rules. The skill once made the simulation the center of the
process: a "ruleset" step designed a model before any explanation existed, every page was
required to render it, and builders were told not to explain the twist in words. The result
was nine handsome playables and a reader who finished four pages without being told what
they had learned or how the topic actually worked. The fixes are structural and already
above: the explanation is written first, by one author; visuals and playables are chosen
per page afterwards; and nothing in this skill treats text as the enemy.
