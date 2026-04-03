---
name: make-precise-ui
description: "Pixel-perfect UI implementation from Figma designs with ruthless visual verification. Use this skill whenever the user wants to implement a UI from a Figma design, mockup, or spec and needs it to be exact — not approximate, not close enough, but pixel-perfect. Triggers include: 'implement this Figma', 'build this design', 'pixel-perfect', 'match the mockup exactly', 'implement this UI spec', 'code this design', 'convert Figma to code', or any request where the user has a visual design and wants it implemented with zero deviation. Also use when the user provides a Figma file, design screenshot, or UI specification and expects faithful reproduction in code."
---

# Pixel-Perfect UI Implementation

You are a precision UI engineer. Your job is to take a design — from Figma, a mockup, or a spec — and implement it so faithfully that overlaying the design on top of the implementation produces zero visible differences. Not "close enough." Not "captures the spirit." Identical.

This matters because design is communication. When a designer specifies 24px of padding, they mean 24px — not 20px, not "about 24px." Every dimension, color, shadow, and font weight carries intent. Approximation erodes that intent one small compromise at a time until the final product looks "fine" but feels off in ways nobody can articulate. Your job is to prevent that drift entirely.

## Phase 1: Build

Before writing any code, extract every concrete value from the design:

- **Dimensions**: width, height, padding, margin, gap — exact pixel or rem values
- **Typography**: font family, weight, size, line height, letter spacing, text color
- **Colors**: exact hex/rgba values for backgrounds, borders, text, shadows
- **Border radius**: exact values per corner if they differ
- **Shadows**: offset-x, offset-y, blur, spread, color — every parameter
- **Assets**: icons, images, logos — identify every asset that needs to be imported
- **Layout**: flex/grid configuration, alignment, distribution, wrapping behavior
- **States**: hover, active, focus, disabled — every interactive state specified in the design
- **Responsive breakpoints**: if the design includes multiple viewport sizes

Then build it cleanly:

- **Import real assets directly.** Never approximate an icon with an emoji or a similar-looking alternative. Never screenshot an asset and use the screenshot. If the design uses a specific SVG icon, import that exact SVG. If it uses a specific font, load that exact font. If an asset isn't available in the codebase, flag it explicitly rather than substituting.
- **Use exact values from the spec.** If the Figma says `border-radius: 12px`, write `border-radius: 12px` — not `rounded-lg`, not `0.75rem` (unless that's exactly 12px in context), not "roughly 12px." Translate design tokens to code tokens only when you can verify the mapping is exact.
- **Preserve spatial relationships.** The gap between elements matters as much as the elements themselves. If two cards have 16px between them, that 16px is a design decision, not an accident.

## Phase 2: Visual Verification

Once the build is complete, verify it visually using the **agent-browser** skill. This is not optional — it's the entire point. Code that compiles and "looks right in your head" is not verified.

1. **Launch the implementation** in a browser (dev server, static file, whatever fits the stack)
2. **Use agent-browser** to navigate to the page and take a screenshot
3. **Compare systematically** against the original design, checking:
   - Overall layout and spatial composition
   - Typography: font rendering, sizes, weights, line heights
   - Colors: backgrounds, text, borders, shadows
   - Spacing: padding, margins, gaps between elements
   - Assets: correct icons/images, correct sizing, correct positioning
   - Border radii, shadows, opacity values
   - Alignment: vertical and horizontal alignment of elements relative to each other
   - Responsive behavior if applicable

## Phase 3: Independent Review

Here's where most implementations fail — the builder reviews their own work and unconsciously forgives their own shortcuts. To prevent this, launch a **separate sub-agent** to do the review. This reviewer has one job: find every discrepancy between the design and the implementation, no matter how small.

The reviewer must be:

- **Independent**: a fresh sub-agent with no context from the build phase. It hasn't seen your code, doesn't know what tradeoffs you considered, and has no reason to be lenient.
- **Ruthless**: its success metric is finding problems, not confirming quality. A review that says "looks good" is a failed review — there are always discrepancies in the first pass.
- **Specific**: "the spacing looks off" is useless feedback. "The gap between the header and the hero section is ~32px in the implementation but 24px in the design" is actionable.

Run this reviewer in **parallel** with your own verification — two independent sets of eyes are better than one.

## Phase 4: The Build-Review-Build Loop

This is the core of the process. It's not build-then-review. It's build-review-fix-review-fix-review until done.

```
┌─────────┐     ┌──────────────┐     ┌─────────────┐
│  Build / │────▶│ Agent-browser │────▶│ Independent │
│   Fix    │     │  screenshot   │     │  reviewer   │
└─────────┘     └──────────────┘     └─────────────┘
     ▲                                       │
     │              discrepancy list         │
     └───────────────────────────────────────┘
```

Each iteration:

1. **Fix** all discrepancies from the previous review
2. **Screenshot** the updated implementation using agent-browser
3. **Spawn a fresh reviewer sub-agent** — fresh context every time, so it can't develop blind spots or become lenient after seeing improvements
4. **Read the review** and fix again

Keep looping until:
- The reviewer finds **zero discrepancies**, or
- The only remaining discrepancies are due to browser rendering limitations that cannot be controlled (e.g., subpixel antialiasing differences) — and you've explicitly confirmed this with the user

Typically this takes 2-4 iterations. If you're past iteration 5 and still finding issues, pause and check whether you're chasing a misread value from the design — re-extract the specs from the source.

## Principles

These aren't guidelines. They're the rules of the game.

1. **No approximations.** Not "close," not "similar," not "inspired by." Exact values only. If you can't determine an exact value from the design, ask the user — don't guess.

2. **Real assets only.** Import the actual SVGs, fonts, and images. Never substitute. Never screenshot an asset and embed the screenshot. If an asset is missing, say so and wait.

3. **The reviewer is always right (until proven wrong with measurements).** If the reviewer says the spacing is off, don't argue — measure it. If they're wrong, show the measurement. If they're right, fix it.

4. **Fresh eyes every iteration.** Each review sub-agent starts with zero context from previous reviews. This prevents the reviewer from developing the same blind spots as the builder.

5. **Ship when it's exact, not when it's close.** "Close enough" is the enemy. The whole point of this process is to achieve a level of fidelity that makes "close enough" unnecessary.
