# Writing for AI: A Philosophy Guide

## The Core Insight

Modern AI models are brilliant generalists. They don't need hand-holding—they need context about what "good" looks like in your specific situation.

**Think of AI as a genius remote teammate**, not a junior analyst who needs step-by-step instructions.

---

## Two Approaches Compared

### The "Tutorial" Approach (Avoid This)

```
You are an investment analyst. Your job is to analyze stocks.

Step 1: Find the files
Step 2: Extract the data
Step 3: Calculate YoY growth using this formula: (Current / Prior - 1) × 100
Step 4: Build a table with these exact columns...

I will punish you if you use web data. I will reward you if you follow instructions.

Checklist:
- [ ] Did you find the files?
- [ ] Did you calculate growth?
- [ ] Did you build the table?
```

**Problems:**
- Explains things AI already knows (YoY formulas, how to build tables)
- Treats AI like it might misbehave (punishment/reward framing)
- Prescribes process instead of outcomes
- Checklists add noise, not value
- Patronizing tone undermines the collaboration

### The "Teammate" Approach (Do This)

```
Analyze this company like a hedge fund analyst preparing for an investment committee.

What matters to us:
- Trajectory over absolutes (is growth accelerating or decelerating?)
- Contradictions in management statements across quarters
- Sentiment inversion: everyone bullish = crowded trade = higher risk

Data hierarchy: financials.json > transcripts > documents > web (last resort)

Output: One-page executive summary I can scan in 2 minutes.
```

**Why this works:**
- States what you want and why
- Describes your specific definition of "good"
- Trusts AI to figure out the obvious parts
- Reads like internal team philosophy, not a training manual

---

## Skills vs. Slash Commands

| Component | Purpose | Trigger | Length |
|-----------|---------|---------|--------|
| **Skill** | Domain knowledge, philosophy, "how we think" | Auto-invoked by Claude when relevant | Longer (captures expertise) |
| **Slash Command** | Specific action, workflow trigger | User types `/command` | Short (just the task) |

**Rule of thumb:**
- Put "what good looks like" in the **skill**
- Put "do this specific thing now" in the **command**

**Example:**
- Skill: "We think about earnings as trajectory, not snapshots. Contradictions matter. Mixed sentiment is healthier than unanimous bullishness."
- Command: `/earnings-preview AAPL` → "Analyze AAPL before earnings. Use the hedge-fund-analyst skill."

The command triggers the action. The skill provides the judgment.

---

## What to Include vs. Remove

### Include (Signal)
- Your specific definitions of quality
- Domain expertise AI wouldn't naturally have
- Preferences that differ from defaults
- Examples of good output (1-2, not 10)
- Decision frameworks for ambiguous situations

### Remove (Noise)
- Basic formulas and calculations
- Step-by-step instructions for obvious tasks
- Checklists and checkboxes
- Repeated information (file paths mentioned once is enough)
- Punishment/reward framing
- Rubrics that just restate "good is good, bad is bad"

---

## Domain Knowledge is Gold

Here's the thing: **your expertise is exactly what AI needs**.

The original HF skills had 1,000+ lines across 5 files. After distillation, we kept 85 lines in a single skill—and lost nothing of value. Every concept in the final skill came from the originals:

| Kept (Domain Knowledge) | Cut (Noise) |
|-------------------------|-------------|
| "Trajectory over absolutes—acceleration matters more than raw numbers" | "YoY Growth = (Current / Prior - 1) × 100" |
| "Sentiment inversion: unanimous bullishness = crowded trade risk" | "Score 10 = good, Score 1 = bad" |
| "Find contradictions in management statements across quarters" | "Step 1: Open file. Step 2: Read file." |
| "Data hierarchy: financials.json > transcripts > web" | File path repeated 10 times |

**The domain knowledge was excellent.** Concepts like contradiction analysis, sentiment inversion, and trajectory thinking—these are genuine insights that AI wouldn't naturally prioritize without being told.

The problem was never *what* you know. It was wrapping that knowledge in tutorial-style instructions that assume the AI can't figure out basic things.

**Keep sharing your expertise. Just share it like you're talking to a smart colleague, not training a junior.**

---

## The Litmus Test

Before adding a line to your prompt, ask:

> "Would a smart colleague already know this?"

If yes, cut it.

> "Does this explain *what I want* or *how to do something obvious*?"

If it's the latter, cut it.

> "Am I writing this because I don't trust the AI?"

If yes, reconsider. The AI is trying to help. Write like you're collaborating, not supervising.

---

## Quick Reference

**Do:**
- Write like you're briefing a smart remote colleague
- Be opinionated about what "good" means to you
- Focus on outcomes, not process
- Trust intelligence, provide context

**Don't:**
- Explain basic concepts
- Use punishment/reward language
- Create checkbox checklists
- Repeat yourself
- Over-specify every step

---

## One Last Thing

The goal isn't to write less—it's to write *better*. A 50-line prompt full of real domain insight beats a 200-line prompt full of obvious instructions.

Density of insight > length of document.
