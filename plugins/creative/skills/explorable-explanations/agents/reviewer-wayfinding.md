# Brief: reviewer — wayfinding and tree auditor

**Inputs:** `persona.md`, `references/tree-design.md`, and the artifact (storyboard.md +
shared/map.js at checkpoint B; the project folder at C/D).
**Output:** `review/round-N/wayfinding.md`.

Check the tree and the reader's sense of place:
- Run `python scripts/validate_tree.py <project>` and include its output; every WARN needs
  a judgment (real problem or acceptable here).
- Spine alone: does it deliver the persona's "afterwards" items without any branch?
- Each fork: is the prompt a question the persona would feel at that moment? Are both
  children worth taking? Are they genuinely different? Is the fork page teaching
  something itself, or is it a menu? Does returning to the fork show the other path?
- Each branch: length 2–5? Ends in sandbox or rejoin? Uses nothing from a sibling branch?
  Labeled as a side path with its rejoin target?
- Each page: the forward link's text poses the next page's question (not "Next", not the
  title alone). Is it findable without hunting? On mobile too?
- Deep link into three random pages in a fresh browser context: does the page initialize
  sanely, show the "start from the beginning?" hint, and not crash?
- Minimap: is the current node obvious? Visited vs. unvisited vs. locked legible?
  Readable on mobile when opened?
- Ladder rungs: where the storyboard marks "up"/"down"/"both", is there actually a
  concrete↔abstract pairing on screen, linked by interaction?
