# Brief: reviewer — static reader

**Inputs:** `persona.md`, the project folder.
**Output:** `review/round-N/static.md`.

Open every page with JavaScript disabled (or read the HTML and the desktop screenshot's
frozen stage). For each page, in one sentence, what does it explain? Then:
- Does the prose alone state the page's idea, or does it lean on "try it and see" with
  nothing to see? (Major — Victor: the static read must work.)
- Does the frozen stage show a meaningful state (a hand-authored scene), or is it blank
  until interaction? (Major)
- Read the `aria-label`s and any live-region text as a screen-reader user would: is the
  idea recoverable from them? (Major if not)
- Any text that only makes sense after the interaction has happened?
- Across the spine, does the sequence of page ideas read as a THEREFORE/BUT chain when
  you list them in order? Quote the chain you reconstructed.
