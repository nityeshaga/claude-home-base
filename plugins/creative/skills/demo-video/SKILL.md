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

By default this tooling tends to produce a video that looks less like a demo and more like a slideshow, which completely defeats the purpose of a demo video. So before any storyboard, find creative angles: present 3–4 unique non-slideshow concepts that max out the ability to creatively use this tool. Describe each concept in motion verbs — what happens, not what's shown — and check it survives the verb test before presenting it. Order them most-recommended first and say why. The human picks one, or combines several — a fused pick makes a longer film, and that's fine when the human wants the full power shown; build what they picked.

### 2. Gate A — the story table (~3 min of human time)

Write `STORYBOARD.md` per playbook §1 and share the scene table with the human: ~10 rows with beat, timing, **what happens (motion verbs, never frames)**, exact on-screen copy, and the scene's caption line (§6 — leave it blank for scenes that caption themselves), plus the story shape, the one global persistence rule, and the fidelity mandate. The human reacts to copy and story arc only. Wrong story here costs minutes; discovered at the end it costs the whole video.

Surface the key text frames (the claim/kinetic-type copy) explicitly at this gate — they carry the film's voice, they're where dry humor can live, and the human will want to react to them line by line. And if the human answers with the points they'd make if *they* were explaining the feature, treat that as the find of the gate: those points are the film's text-frame skeleton — state each claim on screen and prove it with the scene that follows.

In parallel (agent work, no review): assemble the asset folder and write `frame.md` from the product's real brand — pull actual tokens from the product's CSS, not invented ones. Pin any reference screenshots the human shares into `assets/` — they are the source of truth for rebuilt UI.

### 3. Gate B — the contact sheet (~3 min of human time)

One still per scene at its most visually dense moment, composed as a single labeled image, shared with a one-line caption per frame saying what the frame is doing. All copy real, all brand real. This gate is **pure spatial judgment** — say so when posting, so feedback stays on layout, emphasis, and copy legibility.

Iterate stills until approved — loops are cheap (seconds each). Feedback at this gate can include asset work: generated headshots/illustrations (image-gen subagent at low quality settings suffices), redrawing an element so it reads at a glance, de-jargoning copy for non-technical viewers. If an ask is infeasible or not worth it, say so plainly rather than bending backwards.

When frames rebuild a real product's UI — the product being demoed, or a third-party surface like a chat client — approximate-from-memory fails this gate. Build the skins from real sources: the product's actual CSS and view partials, official logo assets, sampled palettes from the human's reference screenshots. If the human flags fidelity issues, the proven fix is a detail pass with the references in hand and a screenshot-compare loop that iterates until clean, forbidden from touching approved copy or beats.

### 4. Build (agent work, no review)

Write the full composition per playbook §2 and §3: one continuous camera world, one paused GSAP timeline, one sub-comp per scene, reuse before building. The storyboard is law and the approved contact sheet is the visual source of truth — lift its markup directly rather than re-inventing frames. Then the full gate loop: `lint` → `validate` (fix what it raises) → `snapshot` (the only gate that catches sub-comp mount bugs) → draft render. Before posting anything, do frame-grab QA: pull stills at each beat's timestamp and check them against the storyboard row by row. If a subagent did the build, verify its output with your own eyes before sharing — subagent reports are hearsay.

Generate the BGM here too, not after Gate C: call Lyria with an explicit requested BPM (playbook §5), then run `npx hyperframes beats` once and derive the musical beat grid — the detector octave-doubles on calm tracks, so reconcile detected BPM against requested BPM before trusting any timestamp. Author scene boundaries and transitions onto grid times during the build, so the cut lands on the music instead of the music being baked around a locked cut (the failure mode of the Aug 2026 Pro Plus video: fades and lifts frozen into the mix that the timeline was then forbidden to move). Gate C still renders and gets judged silent.

### 5. Gate C — the draft cut (mandatory)

Share the draft-quality MP4. This is the only gate that can catch slideshow-ness — stills of a slideshow and stills of a demo look identical. Tell the human how to judge it: ignore draft-render softness, watch only the motion — does it feel like watching something happen, or frames succeeding each other; does any beat drag or land too fast; does the camera feel like one world. Include an honest self-review naming the weakest beats before they find them.

### 6. Final — captions, audio, high-quality render

Fix what Gate C surfaces — both the human's notes and the weaknesses you named yourself (timeline changes are cheap; draft renders take a couple of minutes, not the tens you'd budget).

**Then caption the film. Always, without being asked.** A demo has no voiceover, so a viewer meeting the product for the first time has nothing telling them what they are watching — they see a competent film and follow none of the argument. These are not transcription captions; there is no audio to transcribe. Each line states in plain language the claim its scene then proves, and it is written at Gate A alongside the rest of the copy so the human judges it at the cheap gate rather than after a render. Playbook §5 holds the rail pattern and the rules; the ones that decide whether it works:

- The rail mounts **outside the camera element** — pans and push-ins must not drag it.
- **One line at a time**, and not every scene gets one. A beat whose own on-screen type already speaks (a typed question, the endcard) stays silent, and so does every whip-pan.
- **No ellipses.** Lines fade out completely between beats, so each has to stand alone — a trailing "…" reads as hesitation, not continuation.
- Open a line's window only after the camera settles, and check it against whatever sits low in the frame at that moment (footers, badges) before it covers it.

The mix enters here, after Gate C, so motion gets judged silent first — but the BGM was generated and beat-mapped back in the build (step 4) and the timeline already sits on its grid, so audio drops in without a re-cut. Whether transitions hard-cut on beats or ride phrases is a musical judgment: on rhythmic tracks, land scene changes on strong beats; on calm drumless underscores the detected grid is a metronome the tracker imposed — pace by phrases and energy lifts instead, and never hard-cut to it. Sound only what the story sources: BGM as a quiet underscore that fades as the wordmark lands; typing sounds only under text a human types on screen, never under the AI's replies — the AI isn't at a keyboard. Calibrate one gain across all SFX clips, and verify every audio change by measurement (LUFS/RMS windows against the previous cut), not by ear.

Then `render -q high`, twice: `final-captioned.mp4` and the clean `final.mp4` with the rail disabled. Ship both — the clean cut is what you want wherever the page already carries copy around the video. Frame-grab QA covers every caption in and out boundary, not just the middle of each window, and you look at the shipping file yourself before it reaches the human.

## The anti-slideshow doctrine (the main thing)

The default authoring instinct — beautiful frames, entrance animations, crossfades — produces a slideshow, which defeats the purpose of a demo. Fight it at the storyboard, not the render. The full doctrine is report.md §6 and playbook §3; the load-bearing rules:

- Storyboard scenes as **actions with cause→effect chains** ("cursor clicks Draft → galley streams in"), never frames. Apply the PDF test, verb test, and cause-and-effect test to every scene before Gate A.
- **Rebuild UI in code so it can perform** — radios fill, stamps flip, text types, buttons depress. Screenshots are witnesses, not protagonists.
- **One continuous camera world** — dollies and whip-pans between stations, never plain crossfades.
- **Add a hand** — a visible cursor that travels, hesitates, and clicks.
- A scene is never done — background keeps performing while the foreground resolves.
