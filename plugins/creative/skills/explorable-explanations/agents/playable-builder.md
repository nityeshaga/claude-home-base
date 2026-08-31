# Brief: playable builder

**Inputs:** the page's card(s) with the playable spec (the orchestrator has already written
the page's prose and built the rest of the tree) (design-patterns.md §2 — the
cause→effect, the rules, what's visible, what the reader changes, the result, where the
model lies, the gate if any), the page file(s) with prose already written, `persona.md`,
`design-plan.md`, `references/build-guide.md` (all), `references/design-patterns.md` §3–4,
and `shared/model.js` if the spec says the model is shared.
**Output:** the page file(s) with `.ex-stage` filled (and `shared/model.js` if you own it);
a handoff note in `build/notes.md`.

Build the playable the spec describes, keeping the rules separate from the drawing.
Hand-author the start so the reader's first action is rewarding; respond generously; let the
reader act directly on the thing. Implement the gate if the spec names one, with
`EX.gate.open()` / `EX.gate.fail()` and a working "Show me how" via `EX.on('hatch', …)`.
Store what the reader changes with `EX.set` so it carries forward and the URL reproduces
it (seeded randomness only). Keyboard equivalents for every pointer action; reduced motion
makes steps discrete.

Before you finish, walk through the spec's cause→effect by hand in your build and confirm
the counter-intuitive result actually appears from the default start. If it doesn't, stop
and report — don't tune parameters until it does.

The prose explains; your playable is the evidence. Don't rewrite the prose, but if a
sentence doesn't match what the playable shows, or if the page never states in words what
the reader will have just seen, flag it in the handoff note. Run `scripts/check_pages.py`
on your page(s) and check both screenshots.
