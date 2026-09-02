# Brief: designer

**Inputs:** `persona.md`, `storyboard.md`, the `frontend-design` skill, and the prose of two
real pages from the storyboard, written out — the longest one and a typical one.
**Output:** the visual system (a stylesheet and a short `design.md` that names the aesthetic
and its rules), applied to those two pages so the author can see them.

What the orchestrator must NOT put in the prompt, because the designer will obey it:

- A viewport size, a "must fit with no scroll" test, a column ratio, or a fixed page height.
  Given a box, a designer makes the content fit the box: `overflow: hidden`, a media query
  that drops line-height, 11px labels. That is cramming, and the skill forbids it — fitting a
  page is the author's job, done by trimming or splitting the content, never by the CSS.
- A layout ("prose left, stage right"). The storyboard decides what each page carries; the
  designer decides how it looks.

What the designer is told instead:

- Who reads this and at what pace. Body text at a size and measure a person reads without
  effort; nothing on the page smaller than the persona could read on their laptop without
  leaning in. If the two sample pages don't fit a laptop viewport at that size, the designer
  says so and returns them as they are — that's a signal to the author to cut, not to the
  designer to shrink.
- Come up with a completely unique aesthetic for this subject and this reader: colour,
  type, spacing, how a diagram sits in the page, how a link looks (obviously clickable, never
  a button row). The creative direction is theirs.
- Where the reader is in the tree must be visible on every page, and the ways forward must
  read as part of the page, not a footer.
