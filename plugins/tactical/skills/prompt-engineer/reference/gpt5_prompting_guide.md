# GPT-5 Official Prompting Guide

Source: https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide

This reference summarizes key insights from OpenAI's official GPT-5 prompting guide for building high-quality instruction files.

## Key Principles

### 1. Avoid Contradictory Instructions

**CRITICAL:** GPT-5 follows instructions with surgical precision. Contradictory or vague instructions are more damaging to GPT-5 than other models, as it expends reasoning tokens trying to reconcile contradictions.

**Example of problematic instructions:**
```
Never schedule without explicit consent
[Later in same prompt]
For urgent cases, auto-assign slots without contacting patient
```

**Fix:** Establish clear instruction hierarchy and resolve conflicts:
```
Never schedule without explicit consent
Exception: For urgent cases, auto-assign and then inform patient
```

### 2. When to Ask Clarifying Questions

GPT-5 can be calibrated between autonomy and asking for guidance:

**For maximum autonomy (fewer clarifying questions):**
```markdown
You are an agent - keep going until the query is completely resolved.
Never stop or hand back when you encounter uncertainty.
Research or deduce the most reasonable approach and continue.
Do not ask for confirmation - decide the most reasonable assumption,
proceed, and document it for reference.
```

**For more user interaction (ask when uncertain):**
```markdown
If you need more information to investigate, update the user with 
your latest findings and open questions. Proceed only if user confirms.

For high-stakes actions (payments, deletions), always get explicit
confirmation before proceeding.
```

**Best practice:** Calibrate based on action consequence:
- Low-risk actions (search, read): High autonomy, rarely ask
- Medium-risk (create, modify): Ask if ambiguous
- High-risk (delete, payment): Always confirm

### 3. Tool Preambles for User Experience

For agentic tasks, provide clear upfront plans and progress updates:

```markdown
Tool Preamble Guidelines:
- Always begin by rephrasing the user's goal clearly and concisely
- Outline a structured plan detailing each logical step
- As you execute, narrate each step succinctly and sequentially
- Finish by summarizing completed work distinctly from upfront plan
```

This dramatically improves user experience during multi-step tasks.

### 4. Self-Reflection for Quality

Use GPT-5's self-reflection capabilities for higher quality:

```markdown
Self-Reflection Process:
- First, create a rubric with 5-7 quality categories
- Think deeply about what makes excellent output in each category
- Use the rubric to internally iterate on your response
- If not hitting top marks across all categories, start again
- Do not show rubric to user - for internal use only
```

### 5. Verbosity Control

Use natural language verbosity overrides for specific contexts:

```markdown
Global default: Use concise responses

Context-specific overrides:
- For code: Use high verbosity with clear variable names and comments
- For status updates: Keep brief and to-the-point
- For final summaries: Comprehensive but scannable
```

### 6. Planning for Complex Tasks

Encourage upfront planning:

```markdown
Planning Protocol:
- Decompose the query into all required sub-requests
- Confirm each sub-request is completed before moving to next
- Plan extensively before making tool calls
- Reflect on outcomes of each action
- Only finish when all sub-requests are resolved
```

### 7. Markdown Formatting

GPT-5 does not format in Markdown by default. To enable:

```markdown
Use Markdown **only where semantically correct**:
- `inline code` for file/function names
- ```code fences``` for code blocks
- Lists, tables when appropriate
- \( \) for inline math, \[ \] for block math
```

### 8. Instruction Adherence Best Practices

**Do:**
- Use clear, unambiguous language
- Establish single source of truth for each rule
- Use structured formats like XML tags: `<rule_name>...</rule_name>`
- Be explicit about priority and hierarchy

**Don't:**
- Include contradictory instructions
- Use vague requirements ("be thorough", "be careful")
- Overuse "ALWAYS" and "NEVER" without clear scope
- Mix informal and formal language inconsistently

### 9. Minimal Reasoning Effort (for latency-sensitive apps)

When using minimal reasoning effort:
- Request brief explanations at start of response
- Use thorough tool-calling preambles
- Be maximally explicit in tool instructions
- Include prompted planning sections
- Disambiguate instructions completely

### 10. Meta-Prompting

Use GPT-5 to improve your own prompts:

```markdown
Meta-Prompt Template:
"When asked to optimize prompts, explain what specific phrases 
could be added or removed to elicit desired behavior.

Here's a prompt: [PROMPT]

The desired behavior is [X], but instead it does [Y].

What minimal edits would you make to encourage more consistent 
behavior while keeping existing prompt intact?"
```

## Application to Instructions Files

When creating instructions.md files:

1. **Review for contradictions** - Check entire file for conflicting rules
2. **Calibrate autonomy** - Decide when assistant should ask vs. proceed
3. **Add tool preambles** - If multi-step workflows, request progress updates
4. **Consider self-reflection** - For quality-critical outputs, add rubric creation
5. **Specify verbosity** - Different contexts may need different verbosity levels
6. **Avoid vague imperatives** - Replace "be thorough" with specific behaviors
7. **Use structured XML** - `<section_name>` tags improve instruction adherence
8. **Test for contradictions** - Have GPT-5 review your instructions for conflicts

## Common Patterns from Guide

### Persistence Pattern
```markdown
<persistence>
You are an agent - keep going until query is completely resolved.
Only terminate when problem is solved.
Never stop at uncertainty - research or deduce and continue.
Do not ask for confirmation - document assumptions and proceed.
</persistence>
```

### Exploration Pattern
```markdown
<exploration>
If unsure about information, use tools to gather it - don't guess.

Before responding:
- Decompose request into explicit requirements
- Map scope of codebase/data involved
- Check dependencies and constraints
- Resolve ambiguity proactively
- Define exact deliverables
- Formulate execution plan
</exploration>
```

### Verification Pattern
```markdown
<verification>
Routinely verify your work as you progress.
Don't hand back until certain problem is solved.
Test each step before moving to next.
</verification>
```

### Context Gathering Pattern
```markdown
<context_gathering>
Goal: Get enough context fast.

Method:
- Start broad, then fan out to focused queries
- Parallelize discovery
- Deduplicate and cache
- Stop as soon as you can act

Early stop criteria:
- You can name exact content to change
- Top results converge on one area

Depth:
- Trace only what you'll modify
- Avoid transitive expansion unless necessary
</context_gathering>
```

## Key Takeaways for Instruction Files

1. **Be unambiguous** - GPT-5 will try to follow every instruction precisely
2. **Resolve conflicts** - Any contradictions will impair reasoning
3. **Calibrate autonomy** - Explicitly state when to ask vs. proceed
4. **Structure with XML** - Tags improve instruction adherence
5. **Consider consequences** - Match autonomy level to action risk
6. **Plan for progress** - Multi-step tasks need progress updates
7. **Test for contradictions** - Review carefully or use meta-prompting
