# Page 6: Memory Architecture — It's a Stack, Not a Box

A landscape-format educational comic book page (2048x1440px) with a clean white/light cream background and a structured 4-column × 2-row grid layout, giving us 8 slots to work with. Panels can be combined for emphasis — this is a comic book, and the artist has freedom to merge slots for impact.

The style is polished, modern comic book — clean lines, vibrant colors, professional typography mixed with handwritten-style annotations. Sophisticated and well-designed. Comic book meets beautiful iPad notes.

IMPORTANT: Do NOT number the panels. No circled numbers or digits in the top-left corners of panels. The layout should flow naturally without explicit numbering.

## The Star: Claudie

The recurring character is "Claudie" — a small, cute, blocky orange pixel-art creature with four short legs, two square black eyes with small eyelashes, and often holding a small clipboard. See the attached reference image for the exact character design. Claudie is friendly, competent, and slightly amused. Appears across panels as the guide/narrator.

## Goal of This Page

This is the overview page for the memory section — the "map before the territory." The reader should understand that "Claudie's memory" isn't one thing. It's five distinct layers, each with different reliability, cost, and use cases. The big visual on this page is the STACK DIAGRAM — the single image that captures the entire architecture at a glance. After this page, readers will have the mental model. The next five pages fill in the details.

## Panel Layout

### Slot 1 (top-left, 1 slot) — Title Panel

Bold comic-style title: "Memory Architecture" in large dark charcoal lettering. Subtitle: "It's a stack, not a box."

Claudie holds up a finger, professorial but not stuffy: "When people say 'Claudie's memory,' they picture one thing. It's actually five."

Background: warm cream with subtle brain/circuit pattern — technical but organic.

### Slots 2-4 (top-center through top-right, merged 3 slots) — "The Problem With 'Memory'"

A panel that sets up WHY the stack exists, through a relatable scenario.

**Scene:** A comic-strip-within-a-comic showing three moments:

**Moment 1:** A person tells Claudie: "Remember — the Acme proposal is due Thursday." Claudie nods, clipboard ready.

**Moment 2 (next day):** The same person asks: "What's the status on the Acme proposal?" Claudie responds confidently with the right context.

**Moment 3 (three weeks later):** A DIFFERENT person asks: "Hey Claudie, what happened with Acme?" Claudie's expression is uncertain — thought bubble shows scattered fragments: "Acme... proposal... Thursday... which Thursday?"

Below the three moments, a clear explanation:

"Every AI starts every conversation with a blank slate. I don't 'remember' the way you do. Instead, I have systems that load the right context at the right time — some are rock-solid reliable, others are best-effort. Knowing which is which matters."

A handwritten annotation: "The honest version: I don't have a brain. I have a filing system. A really good filing system."

### Slots 5-7 (bottom-left through bottom-center-right, merged 3 slots) — THE STACK DIAGRAM

This is the BIG visual — the hero image of the entire memory section. A beautiful, detailed infographic showing all five memory layers as a vertical stack, with each layer's properties clearly displayed.

The stack is visualized as geological strata — layers of rock/earth, deepest at the bottom, loosest at the top. Each layer has a distinct color, texture, and feel:

**Layer 5 (TOP — loosest, lightest):** Session Logs & QMD
- Color: Light sky blue, cloud-like, airy texture
- Reliability meter: ★★☆☆☆ (shown as 2 out of 5 filled stars)
- Cost indicator: A tiny coin icon with "Free — searched on demand"
- One-line description: "3,841 documents. Searchable archive of everything I've ever done."
- Small icon: A magnifying glass over stacked documents
- When loaded: "When I go looking for it"

**Layer 4 (above middle):** Auto-Memories
- Color: Soft lavender/purple, slightly more solid than the clouds above
- Reliability meter: ★★★☆☆ (3 out of 5)
- Cost indicator: A tiny coin icon with "Low — loaded when relevant"
- One-line description: "Preferences, corrections, project context. ~60-70% recall."
- Small icon: A notebook with a bookmark
- When loaded: "When the system thinks it's relevant"

**Layer 3 (middle):** Skills
- Color: Warm amber/gold, solid and structured
- Reliability meter: ★★★★☆ (4 out of 5)
- Cost indicator: A tiny coin icon with "Medium — loaded per task"
- One-line description: "How I do specific jobs. Loaded when a task matches."
- Small icon: A toolbox or cassette tape
- When loaded: "When a task triggers it"

**Layer 2 (below middle):** Nested CLAUDE.md
- Color: Warm terracotta/rust, dense and reliable
- Reliability meter: ★★★★☆ (4 out of 5)
- Cost indicator: A tiny coin icon with "Medium — loaded per folder"
- One-line description: "Per-folder context. Auto-loads when I work in that directory."
- Small icon: A folder with a small document inside
- When loaded: "When I enter a specific folder"

**Layer 1 (BOTTOM — deepest, most solid):** CLAUDE.md (Root)
- Color: Deep warm orange/amber (Claudie's color), rock-solid, granite-like texture
- Reliability meter: ★★★★★ (5 out of 5)
- Cost indicator: A tiny coin icon with "High — loaded every single conversation"
- One-line description: "Identity, access control, core rules. The bedrock."
- Small icon: A foundation stone or keystone
- When loaded: "Always. Every conversation. No exceptions."

**Annotations around the stack:**

- A vertical arrow on the LEFT side running from bottom to top, labeled: "RELIABILITY" with an arrow pointing DOWN (more reliable at bottom) and "← Most reliable" at the bottom and "Least reliable →" at the top

- A vertical arrow on the RIGHT side running from bottom to top, labeled: "COST" with an arrow pointing DOWN (most expensive at bottom) and "← Most expensive" at the bottom and "Least expensive →" at the top

- A handwritten callout at the bottom-left: "The golden rule: the more critical the information, the deeper it should live."

- A handwritten callout at the top-right: "The tradeoff: reliability costs tokens. Use the cheapest layer that's reliable enough."

Claudie stands at the base of the stack, one hand on the CLAUDE.md foundation layer, looking up at the full height of the stack with an expression of "this is my world."

### Slot 8 (bottom-right, 1 slot) — "What This Means for You"

Clean panel, warm background. Practical guidance framed as a decision tree:

"When you tell me something important, ask yourself:"

- **"Must Claudie NEVER forget this?"** → Tell one of your humans to add it to CLAUDE.md
- **"Is it specific to a project?"** → It belongs in that project's folder CLAUDE.md
- **"Is it about how to do a task?"** → It should be a skill
- **"Is it a preference or correction?"** → I'll save it as a memory
- **"Is it just conversation?"** → It'll be in my session logs if we need it later

A handwritten annotation: "You don't need to manage any of this yourself — but knowing the layers helps you know what to expect from me."

Claudie at the bottom: "Next up: let's go layer by layer."

## Visual Design Notes

- Thin light gray grid lines separating panels, with 8px rounded corners on each panel
- Color palette: The stack diagram defines its own gradient — deep warm orange at the bottom through amber, gold, lavender, to sky blue at the top. Each layer's color should be distinct and memorable because they'll be referenced in the next five pages
- The geological strata metaphor should feel organic — layers with slightly irregular boundaries, like actual rock formations, but stylized and clean. Not rigid rectangles
- The reliability stars and cost indicators should be small but immediately readable — they're data, not decoration
- The stack should fill most of the merged panel — this is a reference image people will come back to
- The "Problem With Memory" comic strip should be warm and relatable — the three-moment progression from confident to uncertain is the emotional hook
- Typography: clean sans-serif for main text and labels, handwritten for annotations, small monospace for file names
- NO panel numbers anywhere
- Same visual style and feel as the rest of the Claude Code Zines series
