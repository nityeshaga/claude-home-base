---
name: explorable-explanation-creator
description: Turn any topic, document, analysis, or body of research into an Explorable Explanation — a tree of linked, no-scroll HTML pages where each page is the 80/20 of everything beneath it, the reader clicks into whatever they're curious about, and interactive JavaScript (sliders, simulations, toggles) or visuals carries the ideas prose can't. Use this whenever someone asks for an explorable explanation, an interactive or visual explainer, a multi-page HTML explainer, or to "help me really understand X" — and whenever you'd otherwise reach for a single dense one-page HTML explainer, because this is the next version of that.
---

# Explorable Explanation Creator

A one-page HTML explainer is a big step up from markdown. Its weakness is that it is one page: everything the topic has to say, stacked, and the reader scrolls through all of it whether they care or not. An Explorable Explanation splits that into a tree. The front page is the whole idea at its lowest resolution; every click zooms into one part at higher resolution; the reader spends attention only on the branches they choose. Bret Victor and Nicky Case hand-built pages like this over weeks — we generate them in a session, so the scarce resource is no longer the code, it's the direction. That's where this skill spends its effort.

## What a good page is — four principles

1. **One idea at one resolution: say it fully at this zoom, draw it so it sticks, and let the doors carry everything finer.**
2. **A page is done when a reader who stops here leaves knowing the one thing, and a reader who's curious knows exactly where to click.**
3. **The visual carries the idea; the words carry what the visual can't; the doors carry the rest. Nothing on the page does two jobs.**
4. **Every sentence earns its place by saying what the visual can't. Every door earns its place by promising more, not hiding the point.**

These are the whole standard. A page that is crammed has words doing the visual's job; a page that is thin has the doors doing the page's job. The fix for the first is never a smaller font or a second column — it's splitting, or cutting the sentence the visual already says. The fix for the second is saying more at this zoom, not adding a door.

## The format — rules the principles don't already cover

- **One screen, no scroll, responsive.** Pages are designed responsively and must hold the no-scroll rule at 1366×700 — a browser window on a 13-inch laptop, MacBook Air or regular — as the floor, while using larger windows gracefully and stacking cleanly on a phone. That floor is the size it must definitely work at, not the only size it's built for. The constraint is what forces the resolution; a page that needs to scroll is two pages.
- **The visual sets the height; the prose fits beside it.** The prose column is never taller than the visual. If it is, cut the sentences the visual already says — never shrink the font or add a column.
- **It's a tree, not a menu.** The front page states the crux and offers the first fork. Pages offer one to three doors; children fork again; stop splitting when a page has nothing left a reader would click on. The one sanctioned wide fan is a page whose visual *is* a collection (a map whose regions are doors, a table whose rows are doors).
- **Doors are words, not addresses.** A door's label is the thing the reader is curious about — *components*, *the phones*, *this had a bill* — never a section number or a title-cased heading. The chrome (breadcrumb, map) carries the address; the body never does. The better door sits inside the visual — the slice, the box, the stage the next page explains — but if you'd have to add words to the picture to make a door, the door belongs in the prose.
- **An idea with a parameter gets a mechanic.** A diagram where a diagram will do; a slider, toggle, or step-through where the reader learns more by playing. The default state already explains the page — interaction deepens, never unlocks. Start from `references/mechanics.md` — it's inspiration, not a menu.
- **The theme comes from what the topic literally is.** Every core concept gets an exact counterpart, the theme lives in the chrome, the prose stays plain. If your first theme would fit any topic, it fits this one weakly.
- **The reader always knows where they are:** breadcrumb and depth always visible; the tree map is **on demand only** — a button or a key opens it, it never sits on the page as a permanent sidebar.
- **Stick figures are fun.**

## The process — plan, one gate, build

### 1. Ground

Pin three things before designing anything:

- **The reader** — one paragraph: who they are, what they want, the tone that fits, and what they should be able to do afterwards. Then a short list of **terms they already know and don't know**. This list is not meant to be exhaustive but rather a guide. It's what turns reading level from a vibe into something a reviewer can check; without it, builders calibrate to whoever they imagine, and they imagine someone more fluent than the real reader.
- **The source material** — optional. If the human hands you files, every number and quote traces to them and builders may not invent facts except if something is generally true in the world.

### 2. Plan — the creative phase

This is where the creative energy goes, because a wrong call here is paid on every page downstream while generation is nearly free. Write `plan.md` using `references/plan-template.md`: the tree as an ASCII diagram with a one-line purpose per page, the theme and its metaphor map, the reader and their vocabulary, and for every page its visual or mechanic and its doors. Generate and reject options before committing — the first tree is usually a hub wearing a tree's costume, and the first theme is usually generic.

Then **build the front page for real** — `theme.css`, `nav.js`, `index.html` — and screenshot it. Theme is pure taste, and taste doesn't transfer through a description. The front page is also the exemplar every builder copies, so look at it harder than any other page: a flaw here ships N times. Check it against the doors-are-words rule in particular.

Before presenting, run **the reader's Chad on the plan**: a fresh agent given *only* the reader paragraph and vocabulary list, who reads the purpose sentences cold and flags everything they find complicated. Fix the plan. This costs one agent and catches at the gate what would otherwise surface on 22 built pages.

### 3. The gate

Share `plan.md` and the front-page screenshot together, with your recommended choices and why. Hold here until the human signs off. Edits at this gate cost minutes; the same edits after the build cost a rebuild. If they say stop, stop — never build past the gate on momentum.

### 4. Build — the workflow

On approval, run the bundled workflow. Each builder owns its page's prose column the same way it owns the visual: page-local styles within the theme's tokens, and variation that is semantic — a side-note because it's an aside, a pulled line because it's the one to remember, a term box because a word needs pinning. The theme decides palette, type and spacing; the builder decides how this page's words are set. For every page it runs a builder, then two independent reviews — a **spec checker** (does the page do what plan.md says, in a real browser) and **the Chad reader** (given only the persona and vocabulary, reading cold: can I repeat the idea back, could I point at the picture to do it, do I know where to click, which words would I have to look up, is it too long). A fixer addresses both. Then one crawl of the whole tree for dead doors, orphans and overflow, and one **Chad walk in reading order** for what single pages can't show: the same term glossed five ways, a page that assumes a sibling, a branch that repeats its parent.

```
Workflow({
  scriptPath: "${CLAUDE_PLUGIN_ROOT}/workflows/explorable-build.js",
  args: { dir: "<absolute path to the explorable's folder, containing plan.md, index.html, theme.css, nav.js>" }
})
```

#### Who is Chad:

Chad is the artifact's intended audience wearing the meme personality: he meets it cold, with a job to do, and asks dumb questions out loud without a flicker of shame — because looking dumb costs nothing and getting to the point is everything. The other guy performs intelligence and stays paralysed; Chad just says "wait, what does this word mean?" and wins. He is impossible to impress: a nice metaphor, a careful caveat, a clever turn — none of it lands if it doesn't move his job forward. He never pretends to understand something to look smart, and he doesn't do taste debates ("it adds context" — he's the one it's for, and it didn't). He reviews every part and piece, points at the exact words or element he means, and his last comment is always a bird's-eye view of the whole thing: too long, too busy, wrong shape, or does it land. He doesn't rewrite; he comments.

Here Chad's one piece of context is the reader paragraph and the words-they-know list from `plan.md`. Chad *is* that reader. The fixer treats him as an asset, not an opponent: a bullshit detector running before the real reader does, where every comment is a free preview of where a page fails the person it's for. If it works for Chad, it'll probably work for anyone.

### 5. Deliver

Share the link to `index.html` with what shipped (page count, depth), what the checks and Chad caught and fixed, and honest footnotes — any page still over budget, any place the explanation runs on knowledge rather than sources, anything Chad flagged that you chose to keep. The human trusts the artifact because the process shows its receipts.
