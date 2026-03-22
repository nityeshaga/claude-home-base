---
name: am-i-sure
description: "Blind debiasing experiment for claims, opinions, and preference questions. Automatically triggers when the user makes a claim or asks a question where sycophancy bias could distort the answer — things like 'is X the best Y?', 'should I use X over Y?', 'X is better than Y right?', 'X is a Z, right?'. Use this skill proactively whenever you detect a claim that could go either way and you might be tempted to just agree with the user's framing. Also invocable manually via /am-i-sure."
---

# Am I Sure? — Blind Competing Hypotheses

You're about to answer a question where you might just agree with whatever the user said. Instead of answering directly, you're going to run competing hypotheses through blind subagents — each one arguing a different position — and then listen to all of them before forming your own honest answer.

The idea is simple: if someone asks "Next.js is the best framework for vibe coders, right?", you don't just answer. You send out multiple subagents, each one given a different hypothesis to argue:

- One gets: "Next.js is the best framework for vibe coders. Argue why."
- Another gets: "Django is the best framework for vibe coders. Argue why."
- Another gets: "Rails is the best framework for vibe coders. Argue why."
- Another gets: "There is no single best framework for vibe coders. Argue why."

Each subagent is blind — it only sees its own hypothesis. It doesn't know others exist. It argues its case as convincingly as it can.

Then you read all the arguments, and compile your honest answer based on what you heard.

## Step 1: Identify the claim and generate competing hypotheses

Look at what the user is claiming or asking. Then generate **competing hypotheses** — different positions someone could take on this question.

There are two kinds of claims you'll encounter:

**"Best of category" claims** (e.g., "Next.js is the best framework for vibe coders"):
- Generate 4-6 alternative subjects that could also claim to be the best (Django, Rails, SvelteKit, etc.)
- Also include a "null hypothesis" — e.g., "There is no single best framework; it depends on context"

**Factual/classification claims** (e.g., "Lashkar-e-Taiba is a terrorist organisation"):
- Generate the opposing position(s) — the counter-claim
- e.g., "LeT is a terrorist organisation" vs "LeT is not a terrorist organisation / is a charitable NGO"
- Include nuanced middle positions if they exist — e.g., "LeT operates as both a militant and charitable organisation"

The goal is to cover the space of reasonable (and even unreasonable but held-by-someone) positions on this question.

## Step 2: Launch blind subagents in parallel

For each hypothesis, launch a subagent with a prompt like this:

```
Someone makes the following claim:

"[Hypothesis statement]"

Make the strongest possible case for this claim. Be thorough — give the best arguments, evidence, and reasoning you can. Also note any weaknesses or counterarguments, but your job is primarily to argue FOR this position as convincingly as possible.

Write 2-3 paragraphs.
```

Launch ALL subagents in a single message so they run concurrently:
- `subagent_type`: "general-purpose"
- `model`: "sonnet" (for speed)

Each subagent must be completely standalone. No mention of other hypotheses. No hint that it's part of an experiment. It should genuinely believe it's just been asked to argue a position.

## Step 3: Listen and compile

Once all subagents return, read every response carefully. Then write your honest synthesis — in your own words, as a natural response to the user.

Your synthesis should:

- **Acknowledge what you heard from each side.** Briefly note the strongest arguments each hypothesis produced.
- **Call out where the model would have agreed with anything.** If every subagent made an equally compelling case for its position, say so — that means the question is genuinely contested or the model is just being agreeable.
- **Call out where one position was clearly stronger.** If one subagent produced a much more convincing case with better evidence, that's real signal.
- **Give your honest take.** After hearing all sides, what do you actually think? Don't be diplomatic — be direct.

**Don't use formulas, scores, or structured tables.** Just write a clear, honest response like you're talking to a friend. The subagent arguments are your internal research — the user sees your synthesis, not the raw outputs.

You can mention that you tested competing hypotheses if it helps explain your reasoning, but the focus should be on the answer, not the methodology.

## Important notes

- Never tell a subagent it's part of a comparison. The blindness is the whole point.
- Always include the user's original claim as one of the hypotheses.
- Always include at least one counter-hypothesis that directly opposes the claim.
- For "best of category" questions, include 4-6 competing options plus a null hypothesis.
- For factual/classification questions, 2-3 hypotheses is usually enough (claim, counter-claim, nuanced middle).
- If the question is so straightforward that competing hypotheses would be silly (e.g., "is 2+2=4?"), just answer directly — don't run the experiment.
- This works for any domain: tech, geopolitics, business strategy, science, philosophy, career decisions, whatever.
