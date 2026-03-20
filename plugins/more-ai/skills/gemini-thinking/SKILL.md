---
name: gemini-thinking
description: Get a second opinion from Google's Gemini model on any task. Use this skill when you want an independent perspective from another AI — for example, when debugging a tricky issue, evaluating architectural trade-offs, reviewing code, sanity-checking your reasoning, brainstorming alternatives, or any situation where a different viewpoint would be valuable. Also use when the user explicitly asks you to consult Gemini or get a second opinion.
---

# Gemini Thinking

Consult Google's Gemini model for a second opinion on any task. Run the script, pass your question, and incorporate the response into your own thinking.

## Before You Start

Check if `GEMINI_API_KEY` is set in the environment. If not, ask the user to configure it:

1. Get a Gemini API key from https://aistudio.google.com/apikey
2. Add to `~/.zshrc`: `export GEMINI_API_KEY=your_key_here`
3. Run `source ~/.zshrc`

## Script

```bash
python3 scripts/gemini_think.py "Your question here" [--model MODEL] [--file FILE] [--system INSTRUCTION] [--thinking-budget N]
```

### Options

| Option | Values |
|--------|--------|
| `--model` | `gemini-3-pro-preview` (default, strongest reasoning), `gemini-3-flash-preview` (fast, balanced) |
| `--file` | Path to a file to include as context |
| `--system` | System instruction to guide the model's behavior |
| `--thinking-budget` | Max thinking tokens, 0-8192 (default: 8192 = maximum reasoning depth) |

## When and How to Use

Use this as a thinking tool, not a replacement for your own judgment. Good patterns:

- **Debugging**: Stuck on a bug? Describe the symptoms and code, ask Gemini what it thinks.
- **Architecture**: Weighing two approaches? Describe both and ask for trade-off analysis.
- **Code review**: Pass a file with `--file` and ask for a review.
- **Sanity check**: "Does this logic handle edge cases correctly?" with context.
- **Brainstorming**: "What are alternative approaches to solve X?"

### Example Usage

```bash
# Quick question (uses Gemini 3 Pro with max thinking by default)
python3 scripts/gemini_think.py "What are the trade-offs between REST and GraphQL for a read-heavy internal API?"

# Code review with file context
python3 scripts/gemini_think.py --file src/auth.py "Review this auth module for security issues"

# Fast model for simple questions
python3 scripts/gemini_think.py --model gemini-3-flash-preview "Is it better to use a Set or Array for deduplication in JavaScript?"

# Lower thinking budget for quick answers
python3 scripts/gemini_think.py --thinking-budget 1024 "What's the difference between a mutex and a semaphore?"

# With system instruction for focused feedback
python3 scripts/gemini_think.py --system "You are a senior security engineer" --file config.yaml "Audit this configuration for security concerns"
```

## Guidelines

- Default to `gemini-3-pro-preview` for complex reasoning. Use `gemini-3-flash-preview` for quick factual questions.
- Thinking budget is set to 8192 (max) by default for deepest reasoning. Lower with `--thinking-budget 1024` for faster, cheaper responses.
- Always include relevant context — Gemini can't see the codebase, so pass code via `--file` or inline in the prompt.
- Present Gemini's response as a second perspective, not as authoritative. Synthesize it with your own analysis.
- Don't over-use — reserve for genuinely ambiguous or challenging decisions, not routine tasks.
