---
name: openai-imagegen
description: Generate and edit images using OpenAI's gpt-image-2 model — the highest-quality image generation model available (Arena #1 by +242 points). Use this skill when creating high-quality images, marketing assets, infographics, text-heavy graphics, multi-panel compositions, product mockups, UI mockups, or any image generation task where quality and text accuracy matter. Especially use this when the user needs accurate text in images, multilingual text rendering, character consistency across multiple images, or print-ready output. Triggers on requests like "generate an image", "create a graphic", "make a marketing asset", "design a logo", "create an infographic", or any image creation request.
---

# OpenAI Image Generation (gpt-image-2)

Generate and edit images using OpenAI's gpt-image-2 API — the highest-quality image model available as of April 2026.

## Before You Start

1. Check if `OPENAI_API_KEY` is set in the environment.

2. **If `OPENAI_API_KEY` is NOT available → use ChatGPT Prompt Mode.** Instead of running scripts, output a ready-to-paste prompt the user can copy into ChatGPT. Follow these rules:
   - Output the full image generation prompt in a code block labeled "ChatGPT Prompt"
   - Apply all the prompting best practices from the Prompting Guide below — structure it as background → subject → details → constraints
   - Include recommended settings as a note: quality, size, aspect ratio
   - If the task involves editing, tell the user which image(s) to attach and what instruction to give
   - If the task involves multiple images (e.g., a series), give each prompt separately numbered

3. **If `OPENAI_API_KEY` IS available → use the scripts.** Use the venv Python for all script invocations:

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/skills/openai-imagegen/scripts"
PYTHON="${SCRIPTS_DIR}/.venv/bin/python3"
```

If the venv doesn't exist yet, create it:
```bash
python3.12 -m venv "${SCRIPTS_DIR}/.venv"
"${SCRIPTS_DIR}/.venv/bin/pip" install openai Pillow
```

## Scripts

Use these scripts for all image generation tasks. Always invoke with `$PYTHON`:

### generate_image.py — Create images from text
**Use when:** User wants to create a new image from a text description

```bash
$PYTHON "${SCRIPTS_DIR}/generate_image.py" "prompt" output.png [--quality QUALITY] [--size SIZE] [--format FORMAT] [--preset PRESET] [--n COUNT]
```

### edit_image.py — Modify existing images
**Use when:** User wants to edit an image, use reference images, or do inpainting with a mask

```bash
# Edit with instruction
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "instruction" output.png --image input.png [--quality QUALITY] [--size SIZE]

# Edit with mask (inpainting)
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "instruction" output.png --image input.png --mask mask.png

# Compose from multiple reference images
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "instruction" output.png --image ref1.png --image ref2.png
```

## Script Options

| Option | Values | Default |
|--------|--------|---------|
| `--quality` | `low` (drafts, fast), `medium` (default, good balance), `high` (print-ready — only use when explicitly requested), `auto` | `medium` |
| `--size` | Any `WxH` where both are multiples of 16, max edge 3840px, aspect ≤3:1. Or `auto` | `auto` |
| `--format` | `png`, `jpeg`, `webp` | `png` |
| `--compression` | 0-100 (for jpeg/webp only) | None |
| `--n` | 1-8 (number of images) | 1 |
| `--preset` | `draft`, `social`, `print`, `wide`, `portrait` | None |

### Presets

| Preset | Quality | Size | Format | Best for |
|--------|---------|------|--------|----------|
| `draft` | low | 1024x1024 | jpeg | Quick iterations, brainstorming |
| `social` | medium | 1080x1080 | png | Instagram, social posts |
| `print` | medium | 2048x2048 | png | Print materials, high-res assets |
| `wide` | medium | 1920x1080 | png | Presentations, headers, banners |
| `portrait` | medium | 1080x1920 | png | Stories, mobile, posters |

## Output

Images are saved to the specified output path. For Slack sharing, save to `~/work/` or `/tmp/` and use the `attach:` prefix in your response:

```
Here's your image attach:/tmp/generated-image.png
```

When generating multiple images (`--n > 1`), files are saved as `output_1.png`, `output_2.png`, etc.

## Prompting Guide

### Forget old limitations

gpt-image-2 is a generational leap. It has native reasoning — it thinks about your prompt before drawing. Throw away every instinct from DALL-E, Midjourney, or Stable Diffusion about what AI image generation "can't do." This model:

- Renders text perfectly — full paragraphs, menus, labels, code snippets, multilingual
- Places elements exactly where you tell it to
- Maintains character consistency across multi-panel outputs
- Understands complex spatial layouts, infographics, data visualizations
- Handles dense compositions with dozens of elements
- Searches the web for reference before generating (in thinking mode)

**Be as specific and ambitious as you want.** Describe exactly what you see in your head. The more precise and detailed your vision, the better the output. Don't simplify for the model — it can handle it.

### Prompt structure

Order your prompt for clarity:

1. **Format and dimensions** — What is this? (poster, banner, infographic, comic, UI mockup)
2. **Layout** — Exact placement of elements (top-left, centered, grid arrangement)
3. **Content** — Every piece of text, every visual element, every icon
4. **Style** — Colors (use hex codes), typography (font styles, weights, sizes), mood, aesthetic references
5. **Constraints** — What to exclude, background treatment

### Text in images

Just write the exact text you want. The model renders it accurately. For best results:

- Put literal text in **"quotes"** in the prompt
- Specify font characteristics: "bold sans-serif", "thin monospace", "elegant serif italic"
- Specify placement: "centered at the top", "bottom-right corner", "along the left margin"
- For complex layouts with multiple text blocks, describe each one with its position, size, and style

### Be bold

- Want a full restaurant menu with 30 items, prices, and descriptions? Ask for it.
- Want an infographic with real data labels, axis markers, and a legend? Describe it.
- Want a comic strip where the character looks identical in every panel? Just say so.
- Want a magazine cover with a headline, subtitle, barcode, and pull quotes? Go for it.

### Iteration

Default is `medium` quality — good enough for most uses at ~$0.05/image. Only bump to `high` when the user explicitly asks for print-ready or highest quality output. Use `low` for rapid iteration and brainstorming.

## When to Use This vs Gemini

| Scenario | Use |
|----------|-----|
| Highest quality, client-facing assets | **OpenAI (this skill)** |
| Accurate text in images | **OpenAI** |
| Multi-panel with character consistency | **OpenAI** |
| Quick/cheap generation, exploration | **Gemini** |
| Speed-critical (1-3s generation) | **Gemini** |
| 4K output | **Gemini** (pro model) |
| Budget-sensitive bulk generation | **Gemini** |

## Cost Reference

At 1024x1024:
- Low: ~$0.006/image
- Medium: ~$0.053/image
- High: ~$0.211/image

Default quality is `medium` (~$0.05/image). Only use `high` when the user explicitly requests it.
