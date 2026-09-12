---
name: explorable-explanation
description: Build explorable explanations and interactive tutorials inspired by Nicky Case—a non-linear, interconnected tree of short HTML slide decks, with forks and doors placed naturally inside each slide. Use for requests to build an explorable or playable, including requests inspired by Nicky Case, explorabl.es, or Bret Victor.
---

# Explorable explanation

Build a dense interconnected tree of short HTML slide decks, shaped like the topic deserves—a fingerprint of the topic. Keep the explorable one idea at a time, with paths the reader can choose naturally within each slide.

## Read first

1. [The Explorable Explanations Playbook](references/playbook.md) — the Nicky Case playbook, summarized from public articles and talks, with ideas from Bret Victor and Steven Strogatz. Read once per project to understand why the craft rules exist.
2. [Explorable craft](references/explorable-craft.md) — practical lessons, recurring mistakes, and the details that often go wrong. Read before planning and building, and return to it when reviewing.
3. Look at all three screenshots from Nicky Case's [The Evolution of Trust](https://ncase.me/trust/) ([1](references/evolution-of-trust/01-story-and-invitation.png), [2](references/evolution-of-trust/02-prediction-and-model.png), [3](references/evolution-of-trust/03-sandbox-controls.png)) before planning or building to understand the broad vibes. Take inspiration from Nicky Case, but don't copy what it's doing. Make your own version based on the topic and its needs; everything can change.

## Working rhythm

- Go through the documentation for the topic first.
- Before building, write a detailed, fleshed-out `plan.md` like a scriptwriter scripting the whole reader experience: the opening hook, key passages of writing, what the reader sees, does, and discovers, and how they travel through the branches and transitions. Show what draws them onward and how the journey builds toward the intended learning outcome.
- Use the `frontend-design` skill for the UI.
- Pause and show the first batch before doing the rest.
- Then build out the rest of the explorable.
- Screenshot every slide and rework any that fails the craft rules.
- Afterwards, use a few adversarial subagents to judge the whole experience across Writing, UI, Visuals, and Teaching, find violations against the craft doc, and flag items to fix.
- At the very end, launch a separate subagent to give it a visual identity that’s as memorable as the experience itself with the instructions as given below:

```
Launch a separate subagent to act as a creative director. Have it review the code and visually inspect a few key pages, including the playables. Assume the structure, teaching, and writing are already excellent. Its job is to bring personality to the design.

Ask it to propose a few creative directions that feel specific to this topic. Think at two scales:

- The overall experience: like color, typography, backgrounds, texture, illustration style, motion, and recurring visual motifs that make everything feel part of the same world.
- Individual slides or groups of slides: distinctive treatments for key pages—an expressive character, a surprising SVG illustration, a playful background, a mascot, or a small visual joke that makes an idea stick.

Give it permission to be a radical design thinker with a tasteful restraint. What could make someone recognize this explorable from a single screenshot? Consider shaders or 3D effects combined with images where they would make the experience more interesting. It can use the openai-imagegen skill for image generation.

Keep the clarity and ease of use that already work. Let the personality come from the subject and the experience of learning it.

Have the creative director recommend its strongest ideas, with concrete examples of how it would transform a few existing pages. I want to be able to picture the result.
```

- Optionally, if the user reports that the narritive flow is breaking or the explorable is too dense at some points, launch a subagent to identify gaps in the flow with the instructions as given below:

```
Launch a separate subagent whose job is to review the narrative flow of this whole explorable.

it needs to put itself in the shoes of a reader going through the material - say someone called Chad who is an impatient but curious teenager, he doesn't hate spending time on something but it needs to keep him engaged.

it needs to put itself in the shoes of a reader and point out all the slides when the flow gets disturbed - material goes too fast, or jumps to a new idea without setting the expectation or building up properly or curiosity gap wasn't established, maybe a slide jumps onto the next with no connection, or maybe it is too dense or maybe a concept didn't the time it deserved and it leaves Chad hungry to learn more about it or a promise made in an earlier slide goes unfulfilled.

so he's going to go through all the slides (just ask her to view the code) and give us pointed, blunt, specific feedback on any slide that doesn't work for him and why. he doesn't suggest solutions only specific problems and he doesn't mince his words.
```

- Once its review is in, realize that Chad just did us a big service. It gives us an opportunity to massively improve and enrich the reader experience even further. Lets do an awesome job at filling in these gaps and build a version 2.0 here. Feel free to use subagents to distribute the work.

## Sign the work

A finished explorable carries one quiet credit line, placed where a book puts its colophon — the cover area or the last slide. Never mid-flow.

```html
<div class="who">
  by <strong>Author Name</strong> ·
  made with the <a href="https://github.com/nityeshaga/claude-home-base/tree/main/plugins/creative/skills/explorable-explanations">Explorable Explanations skill</a>
</div>
```

- Name the author first and link them if you know where. The skill's link is the smaller half.
- Style it to recede: small, low contrast, no badge, no logo, no border.
- One line, one place. Never repeated per slide.
- If the author would rather not be named, drop their half and keep the line.
