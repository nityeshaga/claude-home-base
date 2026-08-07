---
name: demo-video
description: Build a product demo video with HyperFrames using the gated taste workflow (concepts → story table → contact sheet → draft cut → final). Use this skill whenever asked to make a demo video, launch video, or feature video for a product — or any HyperFrames video where a human will judge the result. The pipeline works mechanically without gates, but gateless renders have produced slop every time; this skill exists so that never happens again.
---

# Demo Video — the gated HyperFrames workflow

A demo video is built as three artifacts (`frame.md` → `STORYBOARD.md` → the composition) with the human's taste wired in at three cheap gates. The gates are the workflow — skipping them is how the June 2026 CC Events video became slop that got discarded.

## Read first, in this order

1. `references/playbook.md` — the operational layer: composition contract, anti-slideshow code patterns, render ops for this box, media pipeline, gotchas lint won't catch. Read it fully before authoring any HTML.
2. `references/report.md` — the strategy memo: why HTML wins, HeyGen's 5-step method, the three gates, the slideshow trap (§6 is the most important section in either file).

## The process

This is the sequence actually run, gate by gate, on the CC matchmaking video (July 2026). Agent work happens between gates; the human is looped in only at the numbered gates — everywhere else, review just adds latency.

### 0. Understand the product

If cold on the product, spawn a subagent to brief you on it: what it does, its real mechanics, real seed/demo data, what differentiates it. The concepts must be grounded in mechanics that actually exist — every artifact that later appears on screen should be real (real rule semantics, real email subject formats, real seed/demo data — never real customer data).

### 1. Concepts (human picks)

By default this tooling tends to produce a video that looks less like a demo and more like a slideshow, which completely defeats the purpose of a demo video. So before any storyboard, find creative angles: present 3–4 unique non-slideshow concepts that max out the ability to creatively use this tool. Describe each concept in motion verbs — what happens, not what's shown — and check it survives the verb test before presenting it. Order them most-recommended first and say why. The human picks one, or grafts pieces of two together; build what they picked.

### 2. Gate A — the story table (~3 min of human time)

Write `STORYBOARD.md` per playbook §1 and share the scene table with the human: ~10 rows with beat, timing, **what happens (motion verbs, never frames)**, and exact on-screen copy, plus the story shape, the one global persistence rule, and the fidelity mandate. The human reacts to copy and story arc only. Wrong story here costs minutes; discovered at the end it costs the whole video.

In parallel (agent work, no review): assemble the asset folder and write `frame.md` from the product's real brand — pull actual tokens from the product's CSS, not invented ones.

### 3. Gate B — the contact sheet (~3 min of human time)

One still per scene at its most visually dense moment, composed as a single labeled image, shared with a one-line caption per frame saying what the frame is doing. All copy real, all brand real. This gate is **pure spatial judgment** — say so when posting, so feedback stays on layout, emphasis, and copy legibility.

Iterate stills until approved — loops are cheap (seconds each). Feedback at this gate can include asset work: generated headshots/illustrations (image-gen subagent at low quality settings suffices), redrawing an element so it reads at a glance, de-jargoning copy for non-technical viewers. If an ask is infeasible or not worth it, say so plainly rather than bending backwards.

### 4. Build (agent work, no review)

Write the full composition per playbook §2 and §3: one continuous camera world, one paused GSAP timeline, one sub-comp per scene, reuse before building. Then the full gate loop: `lint` → `validate` (fix what it raises) → `snapshot` (the only gate that catches sub-comp mount bugs) → draft render. Before posting anything, do frame-grab QA: pull stills at each beat's timestamp and check them against the storyboard row by row.

### 5. Gate C — the draft cut (mandatory)

Share the draft-quality MP4. This is the only gate that can catch slideshow-ness — stills of a slideshow and stills of a demo look identical. Tell the human how to judge it: ignore draft-render softness, watch only the motion — does it feel like watching something happen, or frames succeeding each other; does any beat drag or land too fast; does the camera feel like one world. Include an honest self-review naming the weakest beats before they find them.

### 6. Final

Fix what Gate C surfaces (timeline changes are cheap — renders on an unloaded box take ~1 minute at draft, not the budgeted 20), then `render -q high` and post the final MP4.

## The anti-slideshow doctrine (the main thing)

The default authoring instinct — beautiful frames, entrance animations, crossfades — produces a slideshow, which defeats the purpose of a demo. Fight it at the storyboard, not the render. The full doctrine is report.md §6 and playbook §3; the load-bearing rules:

- Storyboard scenes as **actions with cause→effect chains** ("cursor clicks Draft → galley streams in"), never frames. Apply the PDF test, verb test, and cause-and-effect test to every scene before Gate A.
- **Rebuild UI in code so it can perform** — radios fill, stamps flip, text types, buttons depress. Screenshots are witnesses, not protagonists.
- **One continuous camera world** — dollies and whip-pans between stations, never plain crossfades.
- **Add a hand** — a visible cursor that travels, hesitates, and clicks.
- A scene is never done — background keeps performing while the foreground resolves.
