---
name: gemini-imagegen
description: Generate and edit images using the Gemini API (Nano Banana). Use this skill when creating images from text prompts, editing existing images, applying style transfers, generating logos with text, creating stickers, product mockups, or any image generation/manipulation task. Supports text-to-image, image editing, multi-turn refinement, and composition from multiple reference images.
---

# Gemini Image Generation (Nano Banana 2)

Generate and edit images using Google's Gemini API.

## Before You Start

1. Check if `GEMINI_API_KEY` is set in the environment. If not present, ask the user to configure it:
   - Get a Gemini API key from https://aistudio.google.com/apikey
   - In Claude Desktop, click the gear icon next to the "Local" dropdown
   - Add `GEMINI_API_KEY=your_key_here` in the Environment variables dialog
   - Click "Save changes"

2. Use the venv Python for all script invocations. The scripts require Python 3.10+ with `google-genai` and `Pillow`:

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/skills/gemini-imagegen/scripts"
PYTHON="${SCRIPTS_DIR}/.venv/bin/python3"
```

If the venv doesn't exist yet, create it:
```bash
python3.12 -m venv "${SCRIPTS_DIR}/.venv"
"${SCRIPTS_DIR}/.venv/bin/pip" install google-genai Pillow
```

## Scripts

Use these scripts for all image generation tasks. Always invoke with `$PYTHON` (the venv python from above):

### generate_image.py - Create images from text
**Use when:** User wants to create a new image from a text description

```bash
$PYTHON "${SCRIPTS_DIR}/generate_image.py" "prompt" output.png [--model MODEL] [--aspect RATIO] [--size SIZE]
```

### edit_image.py - Modify existing images
**Use when:** User wants to edit or transform an existing image

```bash
$PYTHON "${SCRIPTS_DIR}/edit_image.py" input.png "instruction" output.png [--model MODEL] [--aspect RATIO] [--size SIZE]
```

### compose_images.py - Combine multiple images
**Use when:** User wants to merge elements from multiple images (up to 14)

```bash
$PYTHON "${SCRIPTS_DIR}/compose_images.py" "instruction" output.png image1.png [image2.png ...] [--model MODEL] [--aspect RATIO] [--size SIZE]
```

### multi_turn_chat.py - Iterative refinement
**Use when:** User wants to refine an image through multiple rounds of feedback

```bash
$PYTHON "${SCRIPTS_DIR}/multi_turn_chat.py" [--model MODEL] [--output-dir DIR]
```

## Script Options

| Option | Values |
|--------|--------|
| `--model` | `gemini-3.1-flash-image-preview` (default, fastest, best instruction following), `gemini-3-pro-image-preview` (fallback / best quality, text rendering, 4K), `gemini-2.5-flash-image` (stable/GA, legacy) |

**Model selection:** Try `gemini-3.1-flash-image-preview` first (fastest, great quality). If it fails or the result is unsatisfactory (e.g., poor text rendering, complex composition), fall back to `gemini-3-pro-image-preview` which produces studio-quality output at the cost of speed.
| `--aspect` | 1:1, 1:4, 1:8, 2:3, 3:2, 3:4, 4:1, 4:3, 4:5, 5:4, 8:1, 9:16, 16:9, 21:9 |
| `--size` | 512 (3.1 flash only), 1K, 2K, 4K (pro only) |

## Prompting Tips

Write prompts like Midjourney experts - be detailed and specific:

- **Photorealistic:** Include camera details (lens, lighting, angle, mood)
  > "A photorealistic close-up portrait, 85mm lens, soft golden hour light, shallow depth of field"
- **Stylized art:** Specify style, outlines, shading explicitly
  > "A kawaii-style sticker of a happy red panda, bold outlines, cel-shading, white background"
- **Text in images:** Use pro model, be explicit about font and placement
  > "Logo with text 'Daily Grind' in clean sans-serif, black and white, coffee bean motif"
- **Product mockups:** Describe lighting setup and surface
  > "Studio-lit product photo on polished concrete, three-point softbox setup, 45-degree angle"
