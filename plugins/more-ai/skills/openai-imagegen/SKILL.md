---
name: openai-imagegen
description: Generate and edit images using OpenAI's GPT-Image-2.6 models (Sunburst for detailed work, Flare for fast iteration). Also makes animated GIFs, SVGs and transparent PNGs, and does markup-guided edits. Use this skill when creating high-quality images, marketing assets, infographics, text-heavy graphics, multi-panel compositions, product mockups, UI mockups, short animated GIFs, vector logos and icons, or any image generation task where quality and text accuracy matter. Especially use this when the user needs accurate text in images, multilingual text rendering, character consistency across multiple images, or print-ready output. Triggers on requests like "generate an image", "create a graphic", "make a marketing asset", "design a logo", "create an infographic", or any image creation request.
---

# OpenAI Image Generation (GPT-Image-2.6)

Generate and edit images using OpenAI's GPT-Image-2.6 API, released November 2026. It comes as two models:

| Model | ID | Use for | Typical time at 1024x1024 |
|-------|----|---------|---------------------------|
| **Sunburst** (default) | `gpt-image-2.6-sunburst` | Detailed compositions, final assets, careful edits | 20-50s |
| **Flare** | `gpt-image-2.6-flare` | Drafts, iteration, anything interactive | 10-15s |

Both cost the same per image. Pick Flare when speed matters and Sunburst when the result is the deliverable.

`gpt-image-2` is deprecated and shuts down on February 10, 2027.

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
"${SCRIPTS_DIR}/.venv/bin/pip" install -U "openai>=3.50" Pillow
```

The scripts need `openai>=3.50`. If a script fails with `unexpected keyword argument 'complexity'` (or `markup`, `svg`, `frame_count`), the venv predates the 2.6 models: rerun the `pip install -U` line.

## Scripts

Use these scripts for all image generation tasks. Always invoke with `$PYTHON`:

### generate_image.py — Create images from text
**Use when:** User wants to create a new image from a text description

```bash
$PYTHON "${SCRIPTS_DIR}/generate_image.py" "prompt" output.png [--model MODEL] [--quality QUALITY] [--size SIZE] [--format FORMAT] [--preset PRESET] [--n COUNT]

# Animated GIF
$PYTHON "${SCRIPTS_DIR}/generate_image.py" "A paper plane doing one loop" plane.gif --frames 12 --frame-ms 100

# SVG (vector logo, icon, simple illustration)
$PYTHON "${SCRIPTS_DIR}/generate_image.py" "Minimal fox head logo, flat orange shapes" fox.svg

# Transparent background
$PYTHON "${SCRIPTS_DIR}/generate_image.py" "Sticker of a smiling sun" sun.png --background transparent
```

The output format follows the file extension (`.png`, `.jpg`, `.webp`, `.gif`, `.svg`) unless `--format` is given.

### edit_image.py — Modify existing images
**Use when:** User wants to edit an image, use reference images, point at the thing to change with markup, or do inpainting with a mask

```bash
# Edit with instruction
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "instruction" output.png --image input.png [--quality QUALITY] [--size SIZE]

# Edit with markup — point at what to change
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "Recolor the circled vase yellow. Keep everything else the same. Do not draw the red circle." output.png --image input.png --markup overlay.png

# Edit with mask (inpainting)
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "instruction" output.png --image input.png --mask mask.png

# Animate a still into a GIF
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "Make the flag wave in the wind" flag.gif --image flag.png

# Compose from multiple reference images
$PYTHON "${SCRIPTS_DIR}/edit_image.py" "instruction" output.png --image ref1.png --image ref2.png
```

With `--size auto` an edit can come back at a different resolution than the input. Pass `--size` to pin it.

### Markup edits

Markup is the precise way to say "change this, here". Draw circles, arrows or short notes on a **separate transparent PNG** the same width and height as the first input image, and pass it as `--markup`. Do not flatten the drawing onto the image. Then refer to the marks in the instruction ("the circled vase", "where the arrow points") and tell the model to leave the marks out of the result.

Make the overlay with Pillow:

```python
from PIL import Image, ImageDraw
base = Image.open("input.png")
overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
ImageDraw.Draw(overlay).ellipse((180, 290, 520, 820), outline=(255, 0, 0, 255), width=10)
overlay.save("overlay.png")
```

`--markup` and `--mask` cannot be combined. Prefer markup: masks are only a hint to the model, while markup also carries intent.

## Script Options

| Option | Values | Default |
|--------|--------|---------|
| `--model` | `sunburst`, `flare`, or a full model ID | `sunburst` |
| `--quality` | `low` (drafts), `medium` (good balance), `high`, `xhigh`, `max` (only when explicitly requested), `auto` | `medium` |
| `--complexity` | `low`, `medium`, `high` — how much the model plans before rendering, separate from quality. High helps dense text and complex layouts. Lower it when an edit changes more than was asked. No extra fee | API default (`high`) |
| `--size` | Any `WxH` where both are multiples of 16, max 3840x2160, aspect ≤3:1. Above 2560x1440 is experimental. Or `auto` | `auto` |
| `--format` | `png`, `jpeg`, `webp`, `gif`, `svg` (svg is generate-only) | from the file extension, else `png` |
| `--compression` | 0-100 (for jpeg/webp only) | None |
| `--background` | `transparent` (png or webp only), `opaque`, `auto` | API default |
| `--frames` | GIF only: 2-16 frames | API default (9) |
| `--frame-ms` | GIF only: delay per frame in ms | API default (200) |
| `--svg-model` | SVG only: the text model that writes the SVG | `gpt-6.1-sol` |
| `--markup` / `--mask` | Edit only, see above | None |
| `--n` | 1-10 (number of images; must be 1 for svg) | 1 |
| `--preset` | `draft`, `social`, `print`, `wide`, `portrait` | None |

### GIF and SVG notes

- **GIF:** leave `--size` on `auto`. Frames come back at 512x512; all frames share one pixel budget, so a large frame size is rejected (6 frames at 1024x1024 fails). Describe the motion as one short, loopable action.
- **SVG:** the image model makes a reference picture and a text model redraws it as vector code, so it takes 35-60s and suits logos, icons and flat illustrations, not photos. Editing an SVG is not supported.

### Presets

| Preset | Quality | Size | Format | Best for |
|--------|---------|------|--------|----------|
| `draft` | low | 1024x1024 | jpeg | Quick iterations, brainstorming (uses Flare unless `--model` is given) |
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

GPT-Image-2.6 plans before it draws. Throw away every instinct from DALL-E, Midjourney, or Stable Diffusion about what AI image generation "can't do." This model:

- Renders text perfectly — full paragraphs, menus, labels, code snippets, multilingual
- Places elements exactly where you tell it to
- Maintains character consistency across multi-panel outputs
- Understands complex spatial layouts, infographics, data visualizations
- Handles dense compositions with dozens of elements

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

Iterate on Flare (`--model flare`, or `--preset draft`), then render the keeper on Sunburst. Default quality is `medium`, which is good enough for most uses. Go above it only when the user explicitly asks for print-ready or highest quality output.

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

Billing is by token: $30 per 1M image output tokens, the same for Sunburst and Flare. Measured at 1024x1024 in November 2026:

| Quality | Output tokens | Cost per image |
|---------|---------------|----------------|
| Low | ~820 | ~$0.025 |
| Medium | ~1,450 | ~$0.043 |
| High | ~1,760 | ~$0.053 |

A 9-frame GIF at low quality is ~1,170 tokens (~$0.035). SVG adds the author model's text tokens on top. Larger sizes cost more.
