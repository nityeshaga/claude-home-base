# HyperFrames Operational Playbook

Companion to `report.html` (the strategy memo: 5-step playbook, taste gates A/B/C, slideshow doctrine, Remotion verdict). This file is the **how-to-actually-author** layer, synthesized July 5 2026 from three Opus deep-dives: (1) all 9 installed skill bundles + live CLI v0.7.1 help, (2) dissection of our two real builds (`~/work/cc-courses-video/`, `~/work/cc-events-video/`), (3) HeyGen's open-sourced launch codebases, now cloned at `~/work/hyperframes-research/` — the exemplar to clone from is `hyperframes-launches/cloud-render-launch/` (frame.md + STORYBOARD.md + HANDOFF.md + 10 compositions).

---

## 1. The mental model

A video = **three artifacts authored in sequence**:

1. **`frame.md`** — design law. YAML frontmatter (normative tokens) + prose (taste rules). Key moves from HeyGen's real ones:
   - Colors grouped by **narrative role**, not palette — each hex gets a comment naming its exact job; **one rationed accent** with an explicit "one gesture per frame" law.
   - **Name the brand-breakers, not just the brand** (Do/Don't list: "mint as a fill color", "sharp corners", "a second accent").
   - **Two type ramps**: the product's real web ramp + a blown-up frame-native ramp in vw (1920×1080 needs re-authored type, not scaled type).
   - Motion as named cubic-beziers + per-char typing cadence (`dur-type: 0.045`) + **named signature moves and bans** ("no crossfading the whole film", "no idle hover-wobble").
   - A **squint test** + pre-render self-audit checklist.
2. **`STORYBOARD.md`** — scene table that doubles as the **build manifest**. Header: feature / length / VO-or-not / aspect / pointer to frame.md / **one global persistence rule** ("the same window grows across the film, never a fresh card"). Story shape: named archetype (Before-After-Bridge etc.) + hook + **fidelity mandate** (on-screen artifacts are REAL code/commands, never fake pills). Per scene: verbatim on-screen copy, **"what happens" (motion verbs), not "what's on screen"**, one named transition per seam, rationale per beat. Closing timing table lists the `compositions/*.html` files with time ranges — storyboard → file tree is 1:1.
3. **The composition** — `index.html` master + `compositions/*.html` sub-comps (one per scene).

## 2. Composition contract (the load-bearing rules)

- Root div: `data-composition-id`, `data-width/height`, `data-duration` (governs render length, NOT GSAP length). Clips: `id`, `class="clip"` (**required** or element stays visible the whole video), `data-start` (seconds or clip-ref `"intro + 2"`), `data-duration`, `data-track-index` (temporal lane, NOT z-order; overlapping clips go on different tracks).
- One **paused** GSAP timeline built synchronously at load, registered `window.__timelines["<id>"]` (key must exactly equal the composition id). Every frame is a fresh seek, possibly out of order/parallel — **state must be a pure function of time**.
- Determinism killers: `Math.random`/`Date.now`/rAF/timers, `repeat:-1` (use `Math.floor(duration/cycle)-1`), async timeline construction, `getBoundingClientRect()` at tween time, hover/scroll state.
- **Sub-comps**: everything inside `<template>` in `<body>` (styles/scripts in `<head>` render unstyled — lints clean!); host div id must exactly equal the file's internal id (mismatch = 45s/scene stall + static frames); use `fromTo` not `from` (from desyncs on re-seek); prefix inner IDs with scene id; size everything in **`cqw`/`cqh`** with `container-type:size` on the root.
- **The silent-freeze bug** (HANDOFF.md): root resolution in a sub-comp script MUST be `(document.currentScript && document.currentScript.closest('#root')) || document.querySelector('#root')` — without the fallback the scene renders static only in the full film, fine solo.
- Media: video `muted playsinline`; audio always a separate `<audio>`; both **direct children of the host root** (wrapped video renders black); framework owns playback; fade via timeline `volume` tween; never animate a timed element's dimensions or opacity (wrap it).
- Transforms are a no-op on inline elements; never animate `display/visibility/width/height/top/left` — use `autoAlpha`, scale, x/y.
- Fonts: local `.woff2` + `@font-face` (compiler embeds as data URIs). No Google Fonts `@import` in a render target.

## 3. Anti-slideshow, in code (proven in the courses rebuild)

Slideshow = screenshots in device frames + entrance animations + crossfades. Demo = one continuous camera world + a cursor that acts + UI that performs. The working patterns, all in `~/work/cc-courses-video/index.html`:

- **Camera dolly**: stations side-by-side in a wide flex `#track` (`data-layout-allow-overflow`), camera = `tl.to("#track",{x:-1920,duration:.65,ease:"power3.inOut"})` with a 0.3s blur in/out faking motion blur (`:444-447`).
- **Cursor fly-and-click**: one SVG arrow, absolute tweens to targets, `scale:.82 yoyo repeat:1` press echoed by the button's own scale+color yoyo (`:428-432`).
- **Deterministic typewriter** `typeInto()` (`:375-380`): proxy tween `{n:0}→{n:len}` with `snap:{n:1}`, `onUpdate` slices the string. THE seek-safe text idiom (HeyGen uses the identical trick) — but only with a **clear-guard tween** spanning 0→start that blanks the element on every update. Without it the renderer's probe pass leaves the finished string sitting on frames long before the typing starts, which on the Pro Plus film put the endcard's price over the middle of the movie and cost a full re-render.
- **Stamp flip** preparing→✓ (rotationX card flip, `:419-422`), **radio fill on select** (`:461`), **SVG checkmark stroke-draw** (`:438`), **clip-path inset reveals** (`:393,:487,:490`), **row stitches in** height 0→N (`:496`).
- HeyGen's seam vocabulary (never a plain crossfade): **zoom-through-the-window** (push into a diegetic object, hard-cut at peak blur), **cut-the-curve** (directional 12% slide + fade, carries momentum), **morph-continuity** (matched-geometry element transforms across the seam), **matched-frame hard cut**. Persistent object + matched geometry = the film illusion.
- Transition discipline (skill law): every scene change gets a transition; every element enters via `fromTo`; **exit animations banned except final scene** (the transition IS the exit); ONE primary transition + 1-2 accents per video. Scene-change times come off the beat grid (§5), not round numbers.
- "**A scene is never done**" — background keeps performing while the foreground resolves; the logo lands in moving footage, never a dead frame.

## 4. Render ops on THIS box (8GB M1)

- **Never `npx hyperframes`** — silently exits empty. Source `~/work/cc-events-video/hf-env.sh`; its `hf()` runs the installed `node_modules/hyperframes/dist/cli.js` under `mise exec node@24` (Node 25 breaks sharp) with `SHARP_FORCE_GLOBAL_LIBVIPS=1`.
- Loop: `init` → author → `lint` → `inspect` (layout sweep) → `validate` (console+contrast) → `snapshot` (the ONLY gate that catches sub-comp mount bugs) → `preview` (Studio, port 3002) → `render -q draft -w1` → review → `render -q high`.
- Low-memory mode auto-fires at 8GB: 1 worker, screenshot capture. The ~1s/frame draft budget is worst-case — with streaming encode, real drafts came in far faster twice (a 1,260-frame draft in 71s; a 2,280-frame draft in ~2 min), so iterate freely. "Stopped" background renders often completed anyway — check for the mp4 before rerunning. Wedge at browser launch = memory pressure, probe a trivial page before blaming the HTML.
- `hf()` cd's into its home project directory, so renders land in THAT project's `renders/`, not yours — go fetch the mp4 from there.
- Formats: mp4 / **webm + mov carry transparency** / gif (15fps) / png-sequence. `--resolution landscape-4k` for DPR upscale. `doctor` is the first move on any failure.
- Frame-grab QA: pull stills at timestamps into a `review/` strip (courses pattern) — cheap motion review between draft and final.

## 5. Media pipeline

- **TTS**: installed v0.7.1 `tts` is Kokoro-only and silently ignores `HEYGEN_API_KEY` — to get HeyGen voices + **word timestamps** use `node skills/hyperframes-media/scripts/heygen-tts.mjs "text" -o out.wav --words out.words.json`. Kokoro default voice `af_heart`, speeds 0.7-0.8 tutorial / 1.1-1.2 upbeat.
- **Transcribe**: always pass `--model` explicitly — the `.en` default silently TRANSLATES non-English audio. Quality-check every run (>20% junk → medium.en → API fallback).
- **Captions — narrated**: word groups of 2-6 by energy; karaoke via `tl.to(word,{...}, word.start)`; mandatory exit guarantee per group (`to` opacity 0 + `set` hidden); 15 pre-built styles via `hyperframes add` (`caption-pill-karaoke` = clean default).
- **Captions — demo rail (no voiceover)**: authored argument lines, not transcription — the transcribe/karaoke path has nothing to bite on. Proven pattern in `~/work/cc-pro-plus-video/index.html` (markup `:339`, helper `:418`, cue sheet `:633`): a `#caprail` div mounted **outside the camera/lens element** and marked `data-layout-ignore` so it is fixed to the frame while the world moves under it; one `.cap` per line, absolutely positioned bottom-center, in the film's own type on a chip from the palette (never the colour the story is using as antagonist). Helper is three tweens per line — `fromTo` rise+fade in, `fromTo` out with `immediateRender:false` (without it the chip lights at t=0), then `set visibility:hidden`. Cue rules: one line on screen ever; nothing during a whip-pan; nothing over a beat whose own type speaks; a window opens only after the camera settles and after checking what sits low in frame at that timestamp (footers, badges) — the collision is invisible in the storyboard and obvious in the render. No ellipses between lines: they fade out completely, so a trailing "…" reads as hesitation. Render both cuts (rail on, rail off) and QA every in/out boundary by frame grab.
- **BGM + beat grid**: Lyria via `GEMINI_API_KEY` (we have it) or local MusicGen — call Lyria with an explicit BPM so the grid is known before detection. **No `bgm` CLI command has ever shipped** (verified absent from 0.7.1 through 0.7.99; the hyperframes-media doc describes it anyway) — call Lyria directly via `google-genai` with the same key, and check the generator script into the project so the track is reproducible. Then `npx hyperframes beats [DIR]` writes `beats/<audio>.json` (`{version, audio, beats: [{time, strength}, ...]}`); it finds the track via `data-timeline-role="music"` or an id matching music/bgm/soundtrack. Gotchas: (a) detected BPM octave-doubles on drumless tracks — `--json` prints bpm; if detected ≈ 2× requested, take every 2nd beat; (b) ~10 min per run on this box (headless-Chrome decode) — run once per track, never in a loop; (c) bpm is printed by `--json` but not persisted into the beat file; (d) the grid moves between encodes — an mp3 of the same master shifted the first beat 0.14s and added 4 beats — so analyze the exact file the composition plays, never a transcode; (e) there is no runtime API for the beat file — read the JSON at authoring time and write the times into the GSAP timeline (Studio's beat-snap is authoring-side only). Discipline: the primary seam and scene boundaries land on strong beats; on calm music the grid is phrase markers, not cut points.
- **Volume tweens are ignored by the 0.7.1 runtime** (renders a flat bed) — bake fades into the WAV with ffmpeg, keep the unfaded master beside it, and record the exact filter chain in a comment so nobody re-derives it; a tween re-added on a newer runtime would double-apply.
- **Typing SFX**: clicks only under text a human types on screen, never under AI replies (the AI isn't at a keyboard). One gain calibrated across all clips — per-clip normalization makes the shortest burst the loudest. Verify the mix by measured LUFS/RMS windows against the previous cut, not by ear.
- **remove-background**: u2net, webm+alpha out, CoreML on this M1; text-behind-subject via inverse plate.
- **Audio-reactive**: pre-extract with `extract-audio-data.py` → per-frame `tl.call` sampling; text ≤3-6% scale swing; no equalizer-bar clichés.

## 6. Registry + our component library

- `hyperframes add <name>` installs blocks (standalone sub-comps → `compositions/`) or components (merge-in snippets). `catalog --type block --tag caption-style` to browse; ~110 blocks.
- Best catalog picks for a CC demo: `vfx-iphone-device` (live HTML app on a real device), `code-typing`/`code-diff`, `data-chart`, `apple-money-count`, `x-post` (social proof), `logo-outro`, `flowchart`, finishing layer `grain-overlay`+`vignette`+`shimmer-sweep`. Transitions: `cinematic-zoom`, `whip-pan`, `flash-through-white` (≤2 shader transitions/video).
- **Our own harvested components** (all proven, file:line in courses `index.html`): typewriter+caret, cursor fly-click, camera dolly, stamp flip, checkmark draw, radio fill, clip-path reveals, stitch-in row, grain overlay, warm wash, device chrome, per-scene `<audio>` voiceover pattern (events `:124-129`). Copy from here before building net-new — Jake's rule.

## 7. Gotchas quick-scan (the ones lint won't catch)

Typed text with no clear-guard from t=0 (finished strings leak onto earlier frames; §3) · a caption or overlay mounted inside the camera element (rides the pan) · collapsed root height (content piles top-left, inspect reports 0 issues) · sub-comp styles in `<head>` · host/template id mismatch · media not a direct root child · missing `class="clip"` · transform on inline span · `<template>` around a standalone index.html · `from()`+CSS opacity:0 = never appears · `gsap.set` on unmounted later-scene clips · two timelines writing one property · full-screen linear gradients on dark bg (H.264 banding) · Tailwind: pinned v4.2.4 only, static class lists, no breakpoints/transition-*.

## 8. Workflow discipline (skill law + our gates)

Hard gate: **no HTML before a visual identity exists** (design.md / frame.md — reaching for `#333`/Roboto means you skipped it). Route by workflow skill first (product-launch-video / motion-graphics / faceless-explainer / pr-to-video / etc.). Then our three taste gates from report.html: **A** story table (Slack, ~3 min) → **B** contact sheet stills (Slack, ~3 min) → build → **C** mandatory draft cut for motion judgment → caption rail + audio → final render, captioned and clean. Storyboard scenes written as ACTIONS ("cursor selects option 2, card whips left"), never frames.
