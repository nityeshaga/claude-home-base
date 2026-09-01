# What Carries a Page: Visuals and Playables

Used once the storyboard is settled, when deciding what carries each page. For each page,
pick the medium that makes that idea land. Case's rule of thumb from the 2014 workshop —
text for abstract concepts, graphs for relationships, animation for change over time,
interactives for processes and systems — is the whole menu in one line.

## Contents

1. The menu: matching ideas to media
2. Designing a playable (the message→mechanics exercise)
3. Gates, for playables only
4. Playable patterns
5. Things that have gone wrong

---

## 1. The menu: matching ideas to media

| The idea is… | Reach for | Notes |
|---|---|---|
| a definition, a distinction, a "here's what this is" | **prose + a labeled diagram** | The default. A good diagram with the right three labels does most of the work. |
| a relationship between quantities | **chart** | Real data if it exists; cite it on the page. |
| "what does this actually look like" | **annotated screenshot / photo** | Often the most honest visual for tools, code, places, things. |
| a process with steps | **sequence diagram or numbered frames** | Static frames beat an animation when the reader needs to compare steps. |
| change over time that's hard to see in frames | **small animation** | Autoplaying, short, loopable; the reader watches. |
| a comparison the reader already has a guess about | **place-your-bets reveal** | Ask for the guess, then show; half a playable, very cheap. |
| something said better by a person | **embedded video** (short) | Link out for longer ones. |
| a system worth operating: a surprising result the reader should produce, a space to poke around in, a decision to feel | **playable** | See §2. |


## 2. Designing a playable

A playable earns its place when the reader operating the system is what makes the idea
land — a counter-intuitive result they produce themselves and therefore believe, a space
worth poking around in, a decision they should feel. That's Case's territory: "I do and I
understand."

Once a page has one, do the message→mechanics exercise (Case, "I Do And I Understand"):

1. **State the cause → effect** the reader should discover, as arrows.
2. **Write the fewest rules** whose play produces it — sentences a child could follow. If
   the chain is good, the rules are almost obvious.
3. **Make the model visible.** The whole state on screen, spatial if possible. Start simple.
4. **Hand-author the start** so the first thing the reader does is rewarding.
5. **Note where the model lies**, and say it on the page. A street map is useful *because*
   it's simplified; don't hide that.

Then the text still explains. The playable produces the evidence; the prose states the
claim and says what it means. Case does this after every interaction in *Trust* and
*Polygons* — "See what happened?" followed by the point in words.

If two or more playables use the same system (same entities, same rules), they share one
model and the reader's state carries between them.

## 3. Gates, for playables only

A gate makes the reader do the thing before the forward link appears. Use one when reading
past the playable would defeat the page — the bet must be placed, the puzzle solved. Pages
with pictures don't have gates; their ways forward are simply offered.

| Gate | The reader… | Use when |
|---|---|---|
| open | follows the link whenever | default for all non-playable pages and most playable ones |
| soft | commits a guess, or touches the thing once | the reveal is the lesson (place your bets) |
| hard | solves a task using the idea | everything after depends on this being understood |
| fork | chooses between two paths | the tree branches here |

Hard gates get an escape hatch ("Show me how") after a few failed tries. Gates never demand
dexterity or speed.

## 4. Playable patterns

When a page *is* a playable, these are the shapes that work (Case 2014/2018, Victor 2011):

- **Place Your Bets** — commit a prediction, then reveal. Cheap, and the natural form of a
  BUT. Works for any claim with a right answer.
- **Puzzle It Out** — solve something using the idea; understanding and assessment merge
  (SineRider). Needs a simulable system and a task with many right answers.
- **See → Model → Apply** — generate your own data points, notice the pattern, then use it.
- **Role Play** — a dilemma with stakes and no right answer; good for forks.
- **Reactive Document** (Victor) — draggable numbers in prose; the consequences update in
  the next sentence. Forces the author to show the model.
- **Explorable Example** (Victor) — one nudgeable example, several linked views of it.
- **Ladder step** (Victor) — concrete and abstract views of the same system side by side,
  linked by hover: touch the trajectory, see the car at that moment.
- **Sandbox** — all the controls, minimal guidance. Deepest learning, highest drowning risk.
  Works as the last page, after every piece has been introduced; expose the parameters the
  argument depends on so a skeptic can try to break it.

Craft notes for any of these, from Case's *Neurotic Neurons* post: direct manipulation
(act on the thing itself), a generous response to the first interaction, a large enough
possibility space that it feels like a system rather than an animation with a button, and
clarity over cleverness — kill the cute metaphor that needs its own explanation.

## 5. Things that have gone wrong

- A tree where every page was a playable and no page explained. The reader finished four
  pages and couldn't say what they'd learned. Prose is the explanation; playables are
  evidence.
- A model designed before the explanation, so the pages became views onto mechanics instead
  of steps in an argument.
- A simulation with precise-looking numbers (milliseconds, kilobytes) for a topic whose
  claims weren't quantitative; the review effort went to the numbers instead of the teaching.
- Vocabulary treated as a cost to minimize, so the pages danced around the names the reader
  came to learn.
- A sandbox that was just the earlier widget with sliders.
- Gamification: points, badges, timers. Changes behaviour, not understanding.
