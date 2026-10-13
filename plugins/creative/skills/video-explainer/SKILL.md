---
name: video-explainer
description: Make a narrated explainer video from real screenshots — a walkthrough of a feature, a flow, a release, a codebase or any idea someone wants explained — with highlight boxes that land on the exact word the voice says, a calm Google voice, and a dark framed look. Use when the user asks for a walkthrough video, an explainer video, a video that tells users about something shipped, a narrated tour of an app or flow, or "a video like the fried-ux-review ones".
---

# Video explainer

A 1–4 minute 1920x1080 video. Each scene is a real screenshot framed on the left, a short panel on the right (eyebrow,
title, one to four lines), and green boxes that appear on the screenshot the moment the narration names that thing.
Title card first, close card last. Narration by Google's voice model; no music.

The look and the timing machinery are already built: `scripts/scenekit.py` (scenes, boxes, wipes, panels, title and
close cards, step pips, index.html), `scripts/tts.py` (voice), `scripts/words.py` (word timings), `scripts/shoot.py`
(screenshots plus element rects), `scripts/contact.py` (contact sheets). Your work is the story, the captures and the
cues. Read `references/example-build.py` before writing your own build.py.

## The rules that make it good

1. **Real visuals only.** Screenshots of the real thing, with realistic demo data. Never mock a UI. When the subject
   has no UI (a process, a codebase, an idea), make the visual a real artifact you screenshot: the doc, the code, a
   diagram you draw as an HTML page.
2. **Every claim is checked against the source** before the voice is recorded: the app's views, prompts, docs, code.
   Write each correction in `NOTES.md`. A wrong sentence in a video can't be edited out later without re-recording.
3. **Works with the sound off.** The point of each scene is on screen in the panel, not only in the voice.
4. **Say the plain thing.** One idea per sentence, no hype, no superlatives, no metaphors, no internal talk (PR
   numbers, teammates' names, tickets) when the audience is outside the team.
5. **One box per thing named, on the word that names it.** Cue every box and panel line to a phrase in the narration.
6. **Look at it before handing it over.** Contact sheets, and frames near every highlight. Fix and re-render.

## Workflow

Work in a new project folder (e.g. `~/work/<slug>-video/`). scenekit writes valid HyperFrames compositions for you,
so you do not need the `hyperframes` skill's intake or routing. Read `hyperframes-core` only if you add your own
scene HTML beyond what scenekit makes.

1. **Brief** — write `BRIEF.md`: who watches, the one message, length, the beats (one per scene), the source of truth
   for claims, the demo data. If the user gave an example video they liked, copy its look.
2. **Script** — `narration.json`: `[{"id": "s00", "text": "..."}, ...]`. One scene per beat, 1–4 sentences each,
   ~150 words a minute. s00 is the title, the last is the close.
3. **Capture** — for a web app: run it locally against a scratch/demo database (never a shared or production one),
   seed realistic data, and drive it with Playwright at 1440x900 @2x, calling `shoot()` from `scripts/shoot.py` for
   each beat with selectors for everything the narration will name. Look at every PNG; retake empty, broken or
   test-looking ones. Use `replace=` to show the production URL instead of localhost, `scroll_selector=` when the
   app scrolls an inner panel, and `park_mouse=False` after a `page.hover()` you want in the shot.
4. **Verify** the script against the source (rule 2). Fix wording minimally.
5. **Voice** — `python3 <skill>/scripts/tts.py` (needs `GEMINI_API_KEY`; voice `Charon` by default, `VOICE=` to
   change), then `python3 <skill>/scripts/words.py`. Re-run both for a scene whenever its text changes. Whisper
   misspells names; map them with `Video(fix_words={"chex": "checks"})` so cues still match.
6. **Build** — `build.py` using `Video` from `scripts/scenekit.py` (see the example), then `python3 build.py`.
   A box is `(shot index, rect, show at, hide at or None)`; time a box on an incoming shot ~0.9 s after its wipe so
   it lands after the wipe finishes. Crop narrow pages with `v.crop()` so text reads at video size; the build warns
   when a box runs past a crop. Then `npx --yes hyperframes@0.8.140 check`.
7. **Render** — `npx --yes hyperframes@0.8.140 render -o <name>.mp4`. Also make a Slack-sized copy:
   `ffmpeg -i <name>.mp4 -c:v libx264 -crf 28 -preset slow -c:a aac -b:a 96k <name>-small.mp4` (aim under 25 MB).
8. **Look** — `python3 <skill>/scripts/contact.py <name>.mp4`, open `contact/sheet.jpg`, then the per-scene frames.
   Check: text overflowing the panel, boxes off their target, a box on the wrong shot after a wipe, unreadable
   screenshots, empty states, the audio track present (`ffmpeg -i <name>.mp4 -af volumedetect -f null -`).
   Fix and re-render until clean.

## Handoff

Send the small copy, a link to the full one, the length, and the list of script corrections from `NOTES.md`. Say what
you did not check (for example, that you did not listen to the voice).
