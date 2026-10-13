---
name: video-explainer
description: Make a narrated explainer video built on real material — a walkthrough of a feature, a flow, a release, a codebase or any idea someone wants explained — with visuals that move in time with the words. Use when the user asks for a walkthrough video, an explainer video, a video that tells people about something shipped, or a narrated tour of an app or flow.
---

# Video explainer

A narrated video, rendered with HyperFrames. Read the `hyperframes-core` skill for the composition contract and use
the `hyperframes` CLI to check, preview and render; skip the `hyperframes` skill's intake and routing, and its approval gates unless the user asked to review.
The visual direction is yours to choose for each video. Decide it from the subject and the audience, not from habit:
a launch video for customers, a code tour for engineers and a process explainer for a team should not look alike.
Don't reuse a previous video's look unless the user asks for it.

## What makes it good

1. **Built on real material.** Screenshots of the real app with realistic demo data, the real code, the real doc or drawn diagrams/mock UI when they explain better.
2. **Every claim checked against the source** before the voice is recorded. List corrections in `NOTES.md`.
3. **Visuals move with the words.** When the voice names something, the picture shows it at that moment.
4. **Works with the sound off.** Each scene's point is readable on screen.
5. **Plain narration.** One idea per sentence. No hype, no metaphors, no team-internal talk for an outside audience.
6. **Looked at before it's handed over.** Frames from every scene, fixed and re-rendered until clean.
7. **Length follows the content.** Don't squeeze a topic into a set length; a teaching video can run long.
8. **Free to get creative.** Any JavaScript library that runs in a browser can make a frame: charts, 3D, physics,
   generative art, your own UI. Draw on top of real screenshots and screen recordings, blend them into your own
   scenes, or rebuild part of a screen to animate it, as long as the real material stays recognisable.

## Teaching something

If the video is meant to teach something:

- **Show why, don't state what.** Build each fact on screen from something the viewer already knows: shapes that
  move, split, fold or scale until the result is visible. A formula appears only after the picture has earned it.
- **A few moves, not many facts.** Find the handful of ideas that generate most of the facts, teach those, and
  rebuild the facts from them.
- **Use the learner's own problems.** Apply each idea to a real question from their material, and solve it on screen.

## Tools in `scripts/`

These worked on earlier videos. Use them as references: change them, replace them, or skip them as the video needs.


- `tts.py` — narration with Google's voice model, one wav per scene from `narration.json`
  (`[{"id": "s00", "text": "..."}]`). Needs `GEMINI_API_KEY`; `VOICE=` picks the voice.
- `words.py` — word-level timings for each wav (whisper via `hyperframes transcribe`).
- `timing.py` — scene starts and lengths from the audio, and `cue(scene, phrase)`: the second a phrase is spoken.
  Use it to time animations to words. Whisper misspells names and merges words; map them with `fix_words`, or cue
  on a neighbouring word. `lead_in` starts each scene's voice a beat after the scene, so it never begins on frame 0.
- `shoot.py` — Playwright helper: screenshot a page and record the rects of named elements, so you can point at them.
- `contact.py` — frames from every scene of a render, plus one sheet, for checking.

## Workflow

1. Brief: audience, the one message, length, beats, source of truth. Then choose the visual direction and say it in
   one or two sentences in the brief. Plan the whole video scene by scene before building any of it. Drafts and
   sketches are for checking your own work; don't stop for approval unless the user asked to review them.
2. Think like a scriptwrite and make a script, one scene per beat, ~150 words a minute. Pay attention to making it interesting to the viewer while doing the job you set out to do.
3. Gather the material. For a web app, run it against a scratch or demo database by default.
   If you must use a live app, or production database remove any confidential info from the html you capture and clean whatever demo data you created once the captures are done.
4. Verify the script. Then `tts.py`, `words.py`, `timing.py`.
5. Build the composition, look at still frames of each scene before the full render, then render and make a small copy for chat
   (`ffmpeg -i in.mp4 -c:v libx264 -crf 28 -c:a aac -b:a 96k out-small.mp4`).
6. Run `contact.py` and look. Check for overflowing text, visuals off their target, empty screens, and that the audio
   track has sound. Fix and re-render.

Hand over the small copy, a link to the full one, the length, the script corrections, and what you did not check.
