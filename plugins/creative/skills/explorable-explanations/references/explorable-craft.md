# Explorable craft

The craft of building a great explorable explanation: practical lessons and things that often go wrong.

You are building an immersive experience, a maze, a rabbit hole for the curious reader to get lost in. This is not simply breaking an article into slides. Inspired by Nicky Case, we are taking the idea one level further: a non-linear tree whose structure is a fingerprint of the topic.

## Four dimensions of quality

- **Writing:** Grab the reader’s attention from the start and sustain a natural flow that makes them want to turn the next page.
- **UI:** Make the interface feel fresh, creative, and carefully considered, with attention to every detail.
- **Visuals:** Make every playable, diagram, animation, and sandbox well-crafted, easy to understand, and useful in teaching the idea it serves.
- **Teaching:** Understand where the reader starts, anticipate their confusions, and shape the whole journey around what they should understand or be able to do by the end.

## Form

Give each slide one clear idea and enough room for the reader to absorb it.

An early draft had less than 5% whitespace, compared with roughly 50% in Case’s work. Every page scrolled, every page used the same prose-left, demo-right layout, and each page held two or three ideas - all bad red flags. The whitespace comparison is a useful reference for how much breathing room to give the content, rather than a percentage to hit on every slide.

Let the idea determine the layout. Sometimes a large, simple visual and a sentence or two are enough. Sometimes text should take over the screen; sometimes a process should unfold in steps. Vary the presentation with what you are explaining, and keep interface decoration out of the way.

Aim for about one viewport at a time. If a slide feels crowded, separate the ideas before shrinking or squeezing them. A little scrolling is okay when it makes sense; splitting the content into two slides may work better.

When the next idea depends on something the reader needs to experience, reveal the next step after that meaningful action. Avoid making them click merely to release another sentence.

## Design a non-linear tree

The difference from Case’s linear playables is the non-linear tree. Give readers a choice of which path to take at key turns.

**Let curiosity guide the navigation.** Introduce a path where something on the slide makes the reader want to explore it. That might be a question raised by an experiment, a phrase they want explained, or a component of a diagram they want to look inside.

Give each path a clear reason to exist at that moment. The reader should understand what they are choosing and why it interests them. When the choices feel arbitrary or compete for attention, introduce some of them elsewhere, where they have more context.

Place the link close to the thing that creates the curiosity—or make that thing itself clickable. Make links easy to recognize, while keeping the slide clear and focused.

## Navigation

“A lot of the magic is in these navigation experiences working flawlessly,” so navigation needs extra care.

**A map available at any point.** Let the reader open a map of the whole tree by clicking or using the `m` shortcut. It should show exactly where they are, which pages they have seen, and let them click to go anywhere.

**Resume completed decks.** Revisiting a finished deck should open its last slide, with all gates unlocked and demos in their completed state. Persist progress for each deck.

**Keep the demo stage the same size.** The size of the demo screen should never change based on what loads into it.

**Every navigation affordance is clickable.** Progress dots are buttons, not decoration: a reader who sees dots will click them. Let them jump to any slide already reached. Anything that looks like it shows position must also let the reader move.
