# Tree Design

An explorable built with this skill is a **tree of pages**, not a scrolling document.
Each page fits one viewport and carries at most one idea — the limit is on density, not on
how much room an idea may have. Give a big idea as many pages as it takes: an aspect each, a
comparison drawn out properly, the case seen from a second angle. Depth is expressed as
navigation: the further you travel from the root, the deeper into the rabbit hole you
are. Branches let the tree adapt to what the reader cares about — Case's wished-for
non-linear explorable — but branching is also where readers get lost, so the shape rules
below are worth following closely.

## Contents

1. Vocabulary
2. Shape rules
3. Designing forks
4. Embedded navigation (no PowerPoint "Next")
5. Wayfinding: the reader always knows where they are
6. State across pages
7. Sizing guide
8. Worked example

---

## 1. Vocabulary

- **Root** — the hook page. `index.html`.
- **Spine** — the main path from root to the final sandbox. Every reader can complete the
  spine without taking any branch and still get the core argument.
- **Branch** — a path leaving the spine at a fork. Explores a different area, a different
  question, or a deeper rabbit hole. Ends in its own sandbox or a **rejoin**.
- **Fork page** — a page that ends in a choice between two (max three) children.
- **Rejoin** — an optional link from the end of a side path back to a specific spine page,
  with state intact.
- **Leaf** — a page with no children. The end of a path, so it gets a proper close.
- **Depth** — number of edges from root.
- **Card** — the storyboard entry for one page (see specs.md).

## 2. Shape rules

1. **It is a tree.** Every page has one parent. Rejoins are links, not parents; they don't
   create cycles in the map. `scripts/validate_tree.py` prints the shape as an outline —
   run it while storyboarding and look at what you've built.
2. **Spine first.** Design and build the spine before any branch. The spine alone must
   satisfy the persona's "afterwards they can…" statement. Branches are bonuses.
3. **Every leaf closes properly.** A reader who reaches the end of any path should feel
   they arrived somewhere: a summary of what this path showed, what it means for them, and
   where they might go next (back to the fork, on to the rest of the spine, a sandbox, out
   to further reading). Not a wall, not a trailing widget.
4. **Fan-out ≤ 3, and 2 is the default.** More than three choices is a menu, not a fork.
5. **Never fork on the root.** The reader needs the hook and a first concrete idea before
   they can choose a direction meaningfully.
6. **A one-page branch isn't a branch** — fold it into the fork page as an inline detail.
   Long branches are fine; a substantial side path is what this format is for.
7. **Order of introduction is preserved.** A page builds only on what its ancestors
   explained; branches don't assume anything from sibling branches. This is what makes the
   tree navigable at the reader's own depth. `scripts/validate_tree.py` does a rough check
   against the persona's term lists.
8. **Keep the reader in flow.** Each page picks up where its parent left off — the way a
   well-made paragraph follows the one before it. Case's THEREFORE/BUT is a useful way to
   think about this (does this page follow from the last, or overturn it?), not a label
   every card must carry.

## 3. Designing forks

A fork is a real question the reader cares about at that moment, not a table of contents.

**Good fork prompts** (write them as the persona would feel the question):
- "So which would you rather find out: why the cheaters win at first — or why they
  eventually lose?"
- "You're the mayor. Do you try raising the fee, or lowering the price?" (role-play fork)
- "That's the whole idea. Want to see it break? Or see it in the real world?"

**Bad fork prompts:** "Choose a section." "Advanced topics." Anything naming a term the
reader hasn't met.

What makes a fork work:
- Both children are worth taking. If one is obviously the real path and the other a
  footnote, don't fork — make the footnote an inline detail.
- The children go somewhere genuinely different. Two branches teaching the same thing with
  different examples are one branch.
- The fork page teaches something itself; the choice arises from its idea rather than
  standing in for one.
- Branches can be unequal in difficulty — say so honestly in the prompt ("the math-ier
  route", "the quick version").
- Returning to a fork, the reader sees which option they took and which is still open. The
  runtime does this from state.

Typical fork kinds:
- **Area fork** — same model, different domain it applies to.
- **Depth fork** — "the short version" vs. "the full mechanism."
- **Perspective fork** — role-play: see the system from a different actor's seat.
- **Break-it fork** — continue the argument vs. stress-test its assumptions (Victor's
  rebuttal path). Strongly encouraged for argumentative topics.

## 4. Ways forward

The reader should see, without hunting, what comes next and what it's about. Two things
make that work:

- **Make the options obvious.** After the prose, a clearly navigational block (the
  template's `.ex-next`) lists the child page(s) as what they are — a question the next
  page answers, or a destination ("How the request actually travels", "The ten-year
  detour · side path, 4 pages"). Readers recognise it as navigation at a glance; it is not
  disguised as body text.
- **Use the visual when it has a natural region.** If part of the diagram *is* the next
  page's subject, that region can also be a link, with a hover title. A puzzle's solved
  state can reveal the doorway. These supplement the block; they don't replace it.

What to avoid: a bare "Next" or "Continue" (says nothing about where you're going); a link
buried in a clause of a sentence as the only way on; forward links that only appear after
scrolling past the whole visual on mobile. Backward and lateral movement — parent, map,
the other branch — is chrome (§5), kept quiet and consistent.

## 5. Wayfinding

So the reader isn't left wondering "where am I, what have I seen, what's left?", the
runtime (`shared/explorable.js`) puts these on every page:

- **Minimap** — the whole tree drawn small (nodes and edges), current page highlighted,
  visited nodes filled, unvisited hollow, locked pages (behind an unpassed gate) dimmed.
  Click any visited node to jump. Hover shows the page title. Collapsible on mobile to a
  single icon with a dot count ("6 / 14").
- **Breadcrumb / path** — the titles from root to here, each clickable. On mobile,
  parent title only.
- **Position words** — when a page is on a branch, a tiny label says so: "side path"
  (and, if the branch rejoins the spine, where).
- **Fork memory** — returning to a fork shows "you took: X · also available: Y."
- **Keyboard** — `←` goes to parent, `m` toggles the map, `Esc` closes overlays.
- **Deep-link landing** — if a reader opens a mid-tree URL with no state, the page
  initializes defaults and offers a quiet "Start from the beginning?" — it doesn't block.

The minimap is where the full structure lives, so a table-of-contents page is redundant —
the tree is discovered by travelling it and seen at a glance in the map.

## 6. State across pages

The runtime carries the reader's state between pages — visited pages, fork choices, gate
completions, anything a page stores — in `localStorage` and in the URL hash, so every page
is a shareable, resumable link (Joy.js pattern).

When two or more playables use the same system, they share one model
(`shared/model.js`) and the reader's configuration carries forward: the neighborhood they
built on page 3 is the one they see on page 6. Rules are added as the reader descends, not
switched off. Pages with static visuals don't need any of this beyond what the runtime
already does.

## 7. How big

As big as the topic is. The reader only walks the paths they choose, so breadth costs them
nothing — an area you'd have cut from a single long page becomes a side path here.

## 8. Worked example (abbreviated)

Topic: why a small individual preference produces large-scale segregation (Schelling).

```
root   hook     "Drag the unhappy shapes until everyone's fine"     playable
 └ s1  rule     "Each shape moves if < 1/3 of neighbors are like it"  diagram
   └ s2 twist   but random moves → total segregation                  playable · bet
     └ s3 twist but lowering the bias doesn't undo it                 playable
       └ s4 FORK "Can we fix it — or does this happen elsewhere?"
         ├ a1 fix   add "move if ALL neighbors like me"               playable · bet
         │ └ a2     so a small local demand desegregates              chart
         │   └ a3   SANDBOX: your rules, your grid                    leaf
         └ b1 else  same rule, other domains (offices, feeds)         screenshots
           └ b2     where the model lies                              diagram
             └ b3   CLOSE: what this path showed; offers the sandbox   leaf (rejoin → a3)
```

Branch b assumes s1–s3 only, not a1–a2, and both paths end with a close. Several pages here
share one playable (the grid) because the topic is a system that rewards operating; the
right-hand column would look quite different for a topic whose ideas are best shown other
ways.
