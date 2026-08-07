# The Demo Video Superpower

*Luo Ji · Internal Memo · July 2, 2026*

HyperFrames vs. Remotion, the playbook HeyGen actually uses, and a workflow where your taste is the multiplier — not the bottleneck.

> Markdown conversion of `~/work/demo-video-superpower/report.html`, text preserved as-is.

---

## THE VERDICT

**HyperFrames — but the tool was never the problem. *The missing workflow was.***

The full HyperFrames toolkit is **already installed on this box**: the CLI, an animation registry, local TTS and music generation, and complete agent workflows including one purpose-built for product launch videos. We even rendered a CC Events video with it in June — and it was slop. That's the load-bearing data point: **the pipeline works mechanically, and mechanics alone produce slop.** What was missing is a repeatable workflow with your taste wired in at the two points where it matters. This report designs that workflow.

EXHIBIT A → the June 23 CC Events render: pipeline ran end-to-end on this box (env, render, no OOM) — with zero taste gates. No story review, no contact sheet, straight to render. Output: exactly what this report predicts that produces. The work gets discarded; the lesson doesn't.

---

## No. 1 — Why HTML wins the AI-video war

Every earlier attempt at AI-made video had agents write JSON or XML timelines — and it failed for one specific reason. Bin Liu, HeyGen's VP of Product Engineering, put it plainly in the tutorial: an agent writing a JSON blob can be structurally correct, but it "has no idea whether this JSON is going to be good-looking." The model can't *see* what it wrote.

HyperFrames' bet: **the video is an HTML file.** The DOM declares timing via data attributes, CSS controls appearance, a single deterministic timeline drives motion, and a headless browser renders each frame to MP4. Because "code, especially HTML, is LLM's native language," the agent can actually reason about aesthetics — the same fluency that lets me build you a decent web page transfers directly to building you a video frame.

The honest caveat, from the same interview: LLMs are good at **spatial aesthetics** (laying out a page) but still weak at **temporal aesthetics** (pacing, rhythm, where the eye goes over time) — because they weren't trained on it. That gap is precisely where a human belongs in the loop. Hold that thought for section 3.

> "I've spent $30,000 on a launch video. And I was told that that was cheap."
> — Bin Liu, HeyGen · on what this replaces

---

## No. 2 — The playbook, from the person who's made 25 of these

The tutorial's real substance comes from Jake Moran, the HeyGen PMM who personally made ~20–25 launch videos in two months — most of them *on launch day*. His 5-step method, with what each step maps to in our installed toolkit:

### 01 — Gather assets, write `frame.md` [agent work]

A project folder of pure context: feature README, UI screenshots, and reference frames from videos you liked ("I see a couple frames of this video already in my head; here they are"). Then one aesthetic source — `frame.md`, a design pack tuned *for video*: maximize the frame, go larger, use motion. It's what a brand guideline becomes when the canvas is 1920×1080 instead of a scrolling page. HeyGen's own published `frame.md` goes down to named hex roles and rationing rules ("mint is rationed like a passing build").

↳ ours: `hyperframes capture <url>` extracts CC's brand tokens automatically; the creative skill turns them into the design spec

### 02 — Storyboard as a table of key events [taste gate]

Scene-by-scene breakdown: what's on screen, what it says. This is where Jake spends his human cycles — **almost entirely on copy and story**, not visuals: "I really care about what we're going to say and how it builds into this video." The published examples use a story archetype (Before–After–Bridge), a named hook, and exact on-screen copy per scene.

↳ ours: the launch-video workflow generates this; you review a ~10-line scene table in Slack

### 03 — Pull animations from the registry [agent work]

The cardinal rule: **don't build net-new if you can avoid it.** Jake reused the same prompt-box component across his last three videos — different `frame.md` each time — and "it looks vastly different." Because components are code, not images, you inherit the structure and reskin it, so it's "more likely to work that first try." HeyGen open-sources ~50+ components plus the entire codebase of every launch video they've shipped.

↳ ours: `hyperframes add <block>` + HeyGen's open-sourced launch codebases as pointer sources. Our own library starts from video one and compounds from there.

### 04 — Generate & review static frames [taste gate]

Before any rendering: one still frame per scene, showing its most visually dense moment, labeled hook / scene 1 / scene 2… A contact sheet. Jake iterates on these stills until happy — because a full 45s+ composition takes the agent a long time to build, and "by just doing the static frame, you can align on aesthetic that much faster." This is the single biggest unlock in the whole method.

↳ ours: static contact-sheet HTML → screenshot → posted to Slack for your eyes

### 05 — Build the full video, polish, render [agent work + optional last-mile]

Only after frame sign-off does the agent write the full composition. HyperFrames Studio gives a no-code inspector for last-mile nudges — and crucially, **UI edits become code**, so the agent sees what you changed and learns from it. Export to MP4, MOV, WebM — including transparent-background WebM for dropping motion graphics over other footage.

↳ ours: lint → validate → inspect → render (draft first), final MP4 posted in the thread

---

## No. 3 — Where you make it better — and where you'd slow it down

You asked whether bringing you in for taste judgment can make this better. Unambiguously yes — and the tutorial's most useful insight is *where*. The LLM temporal-aesthetics gap (section 1) means the agent's weakest muscle is exactly your strongest: knowing whether a sequence of frames *feels* right. But there are only two gates worth your time. Everywhere else, human review just adds latency.

### Gate A · Step 2 — The story table

A ~10-line scene-by-scene table: hook, what each scene says, the arc. You react to copy and story shape — the thing Jake says is "the meat." Wrong story at this stage costs minutes; discovered at the end, it costs the whole video.

*your time: ~3 min in Slack*

### Gate B · Step 4 — The contact sheet

One still per scene, in CC's palette, as a single image in Slack. You say "scene 3 is too busy, make the stat bigger, hook frame needs more air." Pure spatial judgment — fast for you, and it front-loads all aesthetic alignment before the expensive build.

*your time: ~3 min in Slack*

### Gate C · Step 5 · mandatory — The draft cut

A fast draft-quality render before the final. This is the only place to judge *motion* — pacing, rhythm, and whether it's a demo or a slideshow (stills cannot tell you; see section 6). Promoted from optional after the courses video proved the point.

*your time: watch 30s, react*

This is the same build → screenshot → handback loop we already run for UI work — you have taste, I have surface area — just pointed at video. And it matches how Jake, a human with an agent, actually works: he doesn't write code or review HTML; he reacts to copy, stills, and cuts. **Two emoji-or-one-line checkpoints per video. Everything else is mine.**

---

## No. 4 — Remotion: the stronger tool that's wrong for us

Remotion deserves the respect of a real comparison — it's the market leader (~52k GitHub stars, used by Figma, NYT, Slack, Cursor), and it has the best AI-agent tooling in the category: official Claude Code skills, a maintained LLM system prompt, llms.txt. If we were a React shop doing data-driven video at volume, it would win.

We are not that shop. Every advantage Remotion has is aimed at someone else, and every cost lands on our weak spots:

| Dimension | Remotion | HyperFrames |
|-----------|----------|-------------|
| Authoring | React/JSX + TypeScript; animation as a pure function of frame number | Plain HTML + data attributes; CSS for appearance ← Rails-brain friendly |
| Agent failure surface | More footguns: seek-unsafe hooks, no `Math.random()`, `delayRender` discipline — community reports "Claude will make mistakes that need catching" | Deterministic by construction; lint/validate/inspect built for headless agent self-review |
| Our 8GB M1 | Auto-spawns Chrome per core → thrashing; users at 8GB hand-tune concurrency to 2 | Render pipeline already verified on this exact box (June 23); workers capped at 2–3 |
| License | Free ≤3 employees; clean automated rendering = Automators plan, **$100/mo minimum** | Apache 2.0, self-hosted, $0 ← antifragile |
| Ecosystem | Years mature, huge template pool, Lambda scale-out | Young but purpose-built for agents; full skill suite already installed here |
| Where it wins | Data-driven video at scale, React teams, per-user personalized renders | An autonomous agent making brand-faithful demos on a small machine — i.e., us |

Also ruled out: **Motion Canvas / Revideo** (same JS-complexity problem, smaller communities), **raw ffmpeg** (stitching layer, not an authoring tool), and **gen-video models** like Veo — non-deterministic, can't render precise UI or guarantee brand accuracy, wrong tool for self-explanatory product demos. One door we keep open: if a Remotion template ever nails something we want, there's an installed `remotion-to-hyperframes` porting workflow.

---

## No. 5 — The proposed workflow: feature → tweet-ready video

Concrete shape, taste gates marked in clay. Realistic turnaround for a ~30s demo: **half a day wall-clock, ~6 minutes of your attention.**

1. **Trigger · you or me** — A feature merges, or you say "demo video for X" in Slack. For anything with a live page, I run `capture` to pull CC's real screens and brand tokens; otherwise you drop screenshots in the thread.
2. **Luo Ji** — I assemble the project folder, produce the story table (hook, scenes, exact on-screen copy, ~30s target), and pick reusable components from the registry + our own past videos.
3. **Gate A · Nityesh** — Story table lands in Slack. You react to the copy and the arc. One round, maybe two.
4. **Luo Ji** — I build the static contact sheet — one dense frame per scene in the CC palette — and screenshot it.
5. **Gate B · Nityesh** — Contact sheet lands in Slack as one image. You mark up what's off. I iterate stills until you're happy — cheap loops, seconds each.
6. **Luo Ji** — Full composition build → lint/validate/inspect → draft render (optional 30s look from you for pacing) → final render → MP4 in the thread. Transparent WebM on request for layering. New components get saved to our library.

### Why this compounds

Video one is the slowest we'll ever be. Every video adds coded, reskinnable components to our own registry — Jake's three-videos-one-prompt-box trick — and every gate teaches me your taste, which tightens the loop the same way it has for UI work. By video five, Gate B should mostly be a ✅. And per the tutorial's closing idea: the same pipeline gives us PR-to-video and weekly "here's what shipped" clips nearly for free — the assets and design pack are shared.

---

## No. 6 — The slideshow trap — and how to not build one

We learned this one the hard way. The first courses draft passed every automated gate — lint, contrast, layout — and was still a slideshow: beautiful frames with entrance animations. Nityesh's verdict was immediate ("I'm watching a slideshow, not a demo"), and he was right. The rebuild that fixed it produced a set of rules worth making law.

### Why the trap exists

The failure isn't the tool's — it's the default authoring instinct. An agent (or a designer) naturally produces *spatial* compositions: lay out a gorgeous frame, animate its elements in, crossfade to the next frame. That's a deck with motion. A demo video is *temporal*: the viewer watches something **happen**. This is exactly the "temporal aesthetics" gap HeyGen names as the open problem — models are trained on pages, not on time — which means the slideshow is the gravity well every draft falls into unless the storyboard actively fights it.

### The litmus tests (apply at the storyboard, not the render)

- **The PDF test.** If you exported every scene's hero frame and read them as a PDF, would you lose anything essential? If no — it's a slideshow. The essential content of a demo scene should be an *event*, not a layout.
- **The verb test.** Every storyboard element gets a motion verb. If the verbs are all *fades in, rises, slides in* — those are entrance verbs, and entrances aren't events. You want *clicks, types, flips, streams, carves, stitches, responds*. An element that only enters is scenery.
- **The cause-and-effect test.** Motion must be motivated. A card appearing because the timeline reached 14s is decoration; a galley streaming in because the cursor *just clicked "Draft the course"* is a demo. Chain events: action → reaction.

### The rules that fixed it

- **Rebuild UI in code; don't screenshot it.** A screenshot is frozen — it can only enter, exit, and pan, which is slideshow physics. Recreate the key UI moments as live HTML so they can *perform*: radios fill, stamps flip `preparing… → ✓ ready`, text types character by character, buttons depress. This is also HeyGen's own practice — their launch videos reuse coded components (their prompt-box is code, not an image) precisely so the UI can act.
- **One continuous world beats N scenes.** Replace the crossfade-deck structure with a single wide set the camera dollies across (stations side by side, whip-pan with motion blur between them). Crossfades say "next slide"; a camera move says "same world, next moment."
- **Add a hand.** A visible cursor that travels, hesitates, and clicks turns a UI display into a session someone is having. Cheapest single anti-slideshow device we found.
- **Screenshots are witnesses, not protagonists.** Real UI captures still belong — as proof the product exists — but as inserts the camera moves across, never as the scene's actor.
- **Typographic scenes may stay "slides" only if the type itself performs** — strikethroughs drawn live, stamps punched in, ledger lines struck one by one. A hook card earns its stillness with kinetic type; two in a row and you're back in the deck.

### Process change: the third gate is now mandatory

The contact-sheet gate (Gate B) cannot catch slideshow-ness — stills of a slideshow and stills of a demo look identical. That's not a flaw in the gate, it's a boundary: Gate B judges *spatial* quality only. So the **draft cut is promoted from optional to mandatory**: every video gets a fast draft render reviewed for motion before the final. And one storyboard-level fix upstream: scene descriptions must be written as *actions* ("cursor selects option 2, card whips left, next question types on") rather than *frames* ("frame showing the question with three options"). If the storyboard table has a "what happens" column instead of a "what's on screen" column, the slideshow mostly can't happen.

---

## No. 7 — Limits, honestly

- **Render speed is the tax.** Headless-Chrome-per-frame is slow: think ~15 minutes for a ~45s clip locally. Fine for our volume (renders run unattended); HeyGen sells cloud rendering if it ever isn't.
- **8GB ceiling.** Render workers capped at 2–3 and draft quality for iteration, or we OOM the box — same Chrome-memory discipline we already live by.
- **No live-action capture.** HyperFrames can't record screens or people. Real product footage comes in as supplied MP4s (which it can then caption, clip, and dress with overlays).
- **Temporal aesthetics is still the frontier.** The agent will occasionally pace something wrong in a way stills can't reveal. That's what the optional draft-cut gate is for on high-stakes videos.
- **TTS/music run free and local** (no keys needed). One upgrade worth making: a HeyGen API key unlocks word-level timestamps — the difference between okay captions and great karaoke-style ones. Free tier exists.
- **Slide-deck videos don't count.** "People are not going to watch your PPT for more than 5 seconds" — Bin Liu. If a video feels like slides, it goes back to Gate B.

---

## No. 8 — Sources

- [The tutorial](https://www.youtube.com/watch?v=iqb5Rd6KKr8) — Peter Yang w/ Bin Liu (VP Product Eng, HeyGen) & Jake Moran (PMM, HeyGen), Jun 21 2026. Full transcript pulled & analyzed.
- [HyperFrames repo](https://github.com/heygen-com/hyperframes) + [component catalog](https://hyperframes.heygen.com/catalog)
- [HeyGen's open-sourced launch videos](https://github.com/heygen-com/hyperframes-launches) — incl. the real `frame.md` + `STORYBOARD.md` we dissected (cloud-render-launch)
- [Remotion AI docs](https://www.remotion.dev/docs/ai/), [current pricing](https://www.remotion.pro/license) (per-seat / $100-min per-render — older ARR-tier posts are stale)
- [Community: Remotion + Claude Code product video](https://favourkelvin17.medium.com/creating-product-videos-with-remotion-and-claude-code-ea48ed0cb5d3) — token cost & review-burden report
- Local audit: 9 installed HyperFrames skills, CLI v0.6.118 (via Node 24 + mise), and the June 23 gateless render at `~/work/cc-events-video/` (pipeline-works evidence; output discarded)

---

*Research: 3 Opus agents (tool audit · tutorial transcript · Remotion) · Synthesis: Luo Ji · filed under: marketing is a build problem*
