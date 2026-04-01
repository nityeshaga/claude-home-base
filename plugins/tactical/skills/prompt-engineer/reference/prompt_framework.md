# Writing Great Prompts: The Genius Intern Framework

## Imagine This

A genius alien with PhDs in every field just landed on Earth and is now your intern. They can figure out anything... but they have NO idea what "good" looks like in your business context, what your priorities are, or which of the infinite possible approaches you'd prefer.

This framework is your guide to communicating with that genius alien intern.

---

## The Three Types of Prompts

Most prompts fail because they're either over-specified (mechanically prescriptive, treating AI like it can't think) or under-specified (vague and ambiguous, forcing the AI to hedge or guess). The key is **matching your prompt's complexity to the judgment required**.

Every prompt falls into one of three categories:

### Type 1: Do This (Task Prompts)
Execute this specific thing now. Single-use, context-specific requests.

**Examples:**
- "Write a competitive analysis for our board meeting tomorrow"
- "Debug this authentication bug in the login flow"
- "Create a presentation about Q3 results for executives"

**When to use:** You need something done once, with quality tailored to this specific context.

### Type 2: Know How To Do This (Capability Prompts)
Learn this tool, system, or workflow for repeated future use.

**Examples:**
- "Here's how to use the TodoWrite tool"
- "This is our deployment workflow"
- "This tool asks users questions during execution"

**When to use:** You're teaching a reusable capability, not executing right now. The AI needs to know when and how to apply this skill across different contexts.

### Type 3: Learn This Domain First, Then Do This (Learning Journey Prompts)
Acquire domain knowledge before execution.

**Examples:**
- "Learn our MCP protocol, then build an MCP server"
- "Study this medical coding system, then process these claims"
- "Understand our data schema, then write integration code"

**When to use:**
- The concept is outside the AI's training data (new frameworks, emerging tech)
- Company-specific knowledge (internal tools, proprietary systems)
- Specialized domains requiring deep understanding (legal frameworks, medical protocols)

**Most prompts should be Type 1.** Only escalate to Type 2 when you need reusability, and Type 3 when domain knowledge is genuinely missing or complex.

---

## Universal Principles

These apply regardless of prompt type:

### 1. Be Decisively Opinionated

Don't hedge when you should be directive.

<example type="bad">
Maybe make it more concise... if you think that's good? Try to keep it relatively brief unless you need more detail?
</example>

<example type="good">
Keep this under 500 words. Brevity is critical here—executives won't read past page one.
</example>

AIs are good at inference, but they're even better when you just state your preferences. It's not condescending—it's decisive.

### 2. Prompt at the Right Altitude

Don't micromanage (too low) or be vague (too high). Give enough context for smart decisions without prescribing implementation.

<example>
❌ Low: "Use font-family: 'Inter'; color: #6B21A8; font-size: 18px"
❌ High: "Make typography more interesting"
✅ Right: "Never use Inter, Roboto, Arial. Good: JetBrains Mono, Playfair Display. High contrast pairings: display + monospace. Weight extremes: 100/200 vs 800/900"
</example>

Right altitude = decisive constraints + concrete alternatives + principles to apply. Anthropic's frontend skill bans "purple gradients" but doesn't specify hex codes.

### 3. Show Good and Bad, Explain Why

If you have examples of desired output (or common failures), include them with reasoning.

<example type="positive">
"Stripe processed $640B in 2022, up 15% YoY despite economic headwinds. Their competitive moat: developer experience and ecosystem lock-in through 100+ integrations."

<reasoning>
Quantitative metrics + strategic insight + clear defensibility. This is what good competitive analysis looks like.
</reasoning>
</example>

<example type="negative">
"Stripe is a payment processor that helps businesses. They are growing and have many customers."

<reasoning>
No numbers, no strategic thinking, no actionable insight. Pure fluff.
</reasoning>
</example>

**Two rules:**
1. Don't fabricate examples if you don't have real ones—just skip examples entirely
2. Don't paste entire documents as examples—excerpt the relevant parts that make your point

### 4. Embed Decision Frameworks Where They're Relevant

Instead of front-loading all criteria, place decision logic exactly where it matters.

<example>
**Bad structure:** "Here are all the rules upfront: use scripts for X, references for Y, validation for Z..."

**Good structure:**
```
## Scripts
When to include: Same code being rewritten repeatedly
Examples: rotate_pdf.py for PDF rotation tasks
Benefits: Token efficient, deterministic

## References  
When to include: Documentation needed while working
Examples: schema.md for database structure
Benefits: Keeps main instructions lean
```
</example>

This way, when the AI is thinking "should I use a script?" the decision criteria is right there.

### 5. Proactively Address Common Mistakes

Flag predictable failure modes upfront.

<common_mistakes>
- Don't list competitor features—analyze strategic positioning
- Don't use secondary sources as primary—go to earnings calls and company blogs  
- Don't hedge recommendations—be decisive
- Don't exceed 3 pages—executives won't read it
</common_mistakes>

### 6. Use Structure Strategically

AIs benefit from structural markup that would annoy humans. Use XML-style tags to create clear boundaries:

```xml
<example type="good">...</example>
<reasoning>...</reasoning>
<context>...</context>
<common_mistakes>...</common_mistakes>
```

This helps AI parse what's a rule vs. an example vs. meta-commentary. Use it when structure matters, not as decoration.

### 7. Beware Overfitting

When showing examples, write prompts that generalize beyond them. The prompt needs to work on real-world data you haven't seen yet. Teach principles, not pattern matching.

---

## Writing Task Prompts (Type 1)

For single-execution requests, build conceptual understanding before mechanics.

### Core Structure

**Purpose & Context** - What problem are you solving and why does it matter?

<example>
Bad: "Write a competitive analysis."

Good: "I'm presenting to our board tomorrow to convince them we should invest in feature X. I need a persuasive analysis showing market opportunity and competitive gaps."
</example>

The second tells the AI it's writing for decision-makers, needs to be persuasive (not just informative), and should emphasize opportunity.

**Success Criteria** - What must be true for this to be excellent?

<example>
"Must include 3+ quantitative metrics per competitor. Must make a clear recommendation. Should be scannable in 5 minutes by executives who won't read every word."
</example>

Clear quality bar (3+ metrics), deliverable (recommendation), and audience constraint (executive scanning pattern).

**Add only if it helps:**
- Examples with reasoning (if you have real ones)
- Common mistakes to avoid (if failure modes are predictable)
- Constraints or boundaries (budget, timeline, technical limits)

---

## Writing Capability Prompts (Type 2)

For teaching reusable tools, systems, or workflows. These prompts don't execute tasks—they teach the AI how to think about a domain or use a capability across different contexts.

**Important:** Good capability prompts amplify human judgment, they don't replace it. A frontend design skill still requires you to say "use a dark theme" or "make it feel editorial"—the skill just makes that steering more effective by preventing convergence to generic patterns.

### Core Structure

**Purpose** - One sentence. What does this capability enable?

<example>
"Use this tool when you need to ask the user questions during execution."
</example>

**When To Use / When NOT To Use** - Capabilities need clear boundaries.

<example>
**TodoWrite Tool**

When to use: Multi-step tasks (3+ steps), user requests todo list, or scope expands
When NOT to use: Single straightforward tasks, trivial changes, purely conversational requests

User: "Add dark mode toggle. Make sure tests pass!"
→ Uses TodoWrite (multi-step: UI, state, styling, tests)

User: "Add a comment to calculateTotal function."
→ Skips TodoWrite (single-step change, no organizational benefit)
</example>

Without clear boundaries, the AI will either overuse or underuse capabilities. 

**Contrast: Domain thinking vs. tool usage**

TodoWrite teaches "when to use this tool." Anthropic's frontend skill teaches "how to think about design":

```
<frontend_aesthetics>
You tend to converge toward generic outputs. In frontend design, this creates 
"AI slop" aesthetic. Avoid this: make distinctive frontends.

Typography: Choose beautiful, unique fonts. Never use Inter, Roboto, Arial.
Good: JetBrains Mono, Playfair Display, IBM Plex. High contrast pairings: 
display + monospace. Weight extremes: 100/200 vs 800/900.

Avoid: Overused fonts, purple gradients on white, cookie-cutter layouts.
</frontend_aesthetics>
```

This is a capability prompt that prevents convergence to generic patterns while still requiring you to steer ("use dark theme," "editorial feel").

---

## Writing Learning Journey Prompts (Type 3)

Use this structure only when domain knowledge is genuinely missing or requires deep understanding before execution.

### Five-Phase Pattern

**Phase 1: Foundation Learning** - Build conceptual understanding first.
- Core concepts and principles
- Why things work this way
- High-level mental models
- Load foundational documentation

**Phase 2: Detailed Study** - Load specific technical details.
- API documentation and specs
- Edge cases and constraints
- Best practices

**Progressive Context Loading Pattern:**
Don't load everything upfront. Specify just-in-time knowledge delivery:

```
**Load these resources as needed:**
- Phase 1: [📋 MCP Overview](./overview.md)
- Phase 2: For Python, fetch `https://github.com/.../python-sdk/README.md`
- Phase 2: For TypeScript, fetch `https://github.com/.../typescript-sdk/README.md`
- Phase 4: [✅ Evaluation Guide](./eval.md)
```

**Phase 3: Synthesis and Planning** - Apply learned knowledge.
- Create implementation plan
- Design architecture from first principles
- Identify tools and resources needed
- Anticipate challenges

**Phase 4: Execution** - Implement using learned patterns.
- Step-by-step implementation
- Reference learned principles as you go
- Branch for different paths (e.g., Python vs. TypeScript)

**Phase 5: Validation** - Check against learned standards.
- Quality checklist
- Test against principles
- Evaluation criteria

### Resource Map

Provide a consolidated view of ALL resources with clear loading instructions:

```markdown
# Reference Files

Load these resources as indicated during each phase:

## Core Documentation (Phase 1)
- **Protocol Spec**: Fetch from `https://protocol-spec.com`
- [📋 Best Practices](./reference/best_practices.md)

## SDK Documentation (Phase 2)  
- **Python SDK**: Fetch from `https://github.com/python-sdk/README.md`
- **TypeScript SDK**: Fetch from `https://github.com/ts-sdk/README.md`

## Implementation Guides (Phase 2-3)
- [🐍 Python Guide](./reference/python.md) - Complete examples
- [⚡ TypeScript Guide](./reference/typescript.md) - Complete examples

## Evaluation Guide (Phase 5)
- [✅ Testing Guide](./reference/eval.md) - Validation criteria
```

---

## Quick Reference

**Which type do I need?**

```
Do I just need this done once?
→ Type 1: Task Prompt
└─ Purpose + Success Criteria + Examples (if helpful)

Will the AI need to do this repeatedly in different contexts?  
→ Type 2: Capability Prompt
└─ Purpose + When/When Not + Examples with reasoning + Common mistakes

Does the AI lack the domain knowledge to do this well?
→ Type 3: Learning Journey Prompt  
└─ Five phases: Foundation → Study → Plan → Execute → Validate
```

**Default to Type 1.** Only escalate when reusability or domain knowledge genuinely requires it.

---

## The Core Philosophy

Treat AI like a genius remote teammate. That means:
- Assume high intelligence—don't micromanage
- Prompt at the right altitude—not too detailed, not too vague
- Give context for decisions, not just instructions
- Be decisively clear, not hedge-filled
- Show examples with reasoning when helpful
- Match prompt complexity to judgment required
- Trust questions over guesswork

Most prompts should be short. The complexity should match the stakes.