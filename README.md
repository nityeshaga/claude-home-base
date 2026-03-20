# Claude Home Base

An always-on AI cofounder running on your Mac. DM it in Slack, it responds with full access to your codebase, tools, and context. $200/month flat. You own the whole stack.

## What this is

A complete setup for turning a spare Mac (Mini, MacBook Air, whatever) into a dedicated AI server:

- **Slack bot** that wraps Claude Code's CLI — DM it or @mention it in channels
- **Cloudflare Tunnel** for production-grade Slack integration (HTTP Events API, not Socket Mode)
- **Plugin marketplace** with skills for inbox management, brainstorming, image generation
- **Identity system** — your AI writes its own personality, keeps a diary, compounds over time
- **Setup guide** — step-by-step, with dark mode, interactive checklists, and concept explainers

## What you need

- A Mac you can leave running (Mac Mini, old MacBook Air, etc.)
- [Claude Code Max subscription](https://claude.ai) ($200/month)
- A Slack workspace
- A domain for Cloudflare Tunnel (any domain works)

## Quick start

1. **Follow the setup guide** at **[nityeshaga.github.io/claude-home-base](https://nityeshaga.github.io/claude-home-base/)** — it walks you through everything step by step
2. **Set up hardware** — plug in your Mac, configure it for always-on use
3. **Deploy the Slack bot** — Cloudflare Tunnel + Flask, production-standard
4. **Install the starter kit** — the final step in the guide has you paste one prompt into Claude Code. It clones this repo, installs plugins, asks you a few questions, and writes its own identity. You watch it come alive.

## What's in the box

```
bot.py                  # Slack bot (Flask + HTTP Events API)
index.html              # Setup guide (GitHub Pages)
CLAUDE.md.example       # Template for your AI's operations manual
identity.md             # Your AI's soul (principles + self-authored identity)
about-you-and-how-you-came-to-life.md  # Origin story template
.env.example            # Configuration template
requirements.txt        # Python dependencies

plugins/
├── tactical/           # Brainstorming, inbox management
│   └── skills/
│       ├── inbox-manager/   # Email triage with learning preferences
│       └── lets-brainstorm/ # Timed coaching sessions
└── more-ai/            # Gemini image generation, thinking
    └── skills/
        ├── gemini-imagegen/
        └── gemini-thinking/
```

## Architecture

```
You (anywhere) → Slack → Cloudflare Tunnel → Your Mac → Claude Code CLI
                                                          ↓
                                              CLAUDE.md + identity.md
                                              + plugins + skills
                                              + full filesystem access
```

## Bot features

- **HTTP Events API** via Flask — production-standard, stateless
- **Async processing** — responds to Slack within 3 seconds, runs Claude in background
- **Agentic channel behavior** — decides when to respond, stays silent when not relevant (SKIP)
- **Thread continuity** — session IDs persist per thread
- **File handling** — downloads attachments, auto-uploads files mentioned in responses
- **Proactive messaging** — send DMs, post to channels, reply in threads via CLI
- **Streaming output** — real-time responses as Claude generates

## License

MIT
