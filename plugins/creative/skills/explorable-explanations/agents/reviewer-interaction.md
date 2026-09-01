# Brief: reviewer — interaction auditor

**Inputs:** `persona.md`, the project folder, `references/playbook.md` §1 and §6,
`references/design-patterns.md` §3 and §5.
**Output:** `review/interaction.md`.

Audit every interactive element and every link on every page against:
1. **Possibility space** — does the stage feel like a system (many things to try, in any
   order) or an animation with a button?
2. **Direct manipulation** — count the in-betweens between the reader's gesture and the
   model change. Zero is the target.
3. **Juice** — what does the first interaction produce? Is it generous and immediate?
4. **Always interactive** — is there any stretch where nothing can be poked?
5. **Crap-interaction** — any click with no meaningful choice (click-to-advance,
   click-to-reveal-text)? Any "Next"/"Continue"? Any gate that is just a click?
6. **Consistency** — do mechanics or rules change between pages in ways that aren't
   additive? Are constraints enforced by the model or by special-case locks?
7. **Clarity over cleverness** — any metaphor or widget that needs its own explanation?
   Any over-explanation (text that restates what the stage already shows)?
8. **Gate fairness** — can every hard gate be solved with what was taught, without
   dexterity? Does the hatch appear after 3 failures and actually demonstrate?
9. **Keyboard + reduced motion** — can you do everything without a pointer? Does the
   page respect prefers-reduced-motion?
10. **Static read** is the static reviewer's job; skip it.

One finding per violation, with the page id and the exact element.
