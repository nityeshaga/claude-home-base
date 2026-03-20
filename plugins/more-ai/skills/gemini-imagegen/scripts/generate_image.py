#!/usr/bin/env python3
"""
Generate images from text prompts using Gemini API.

Usage:
    python3 generate_image.py "prompt" output.png [--model MODEL] [--aspect RATIO] [--size SIZE]

Examples:
    python3 generate_image.py "A cat in space" cat.png
    python3 generate_image.py "A logo for Acme Corp" logo.png --model gemini-3-pro-image-preview --aspect 1:1
    python3 generate_image.py "Epic landscape" landscape.png --aspect 16:9 --size 2K

Environment:
    GEMINI_API_KEY - Required (set via Claude Desktop environment settings)
"""

import argparse
import os
import sys
from typing import Optional

from google import genai
from google.genai import types


API_KEY_ERROR = """
GEMINI_API_KEY environment variable not set.

To configure your API key in Claude Desktop:
1. Get your Gemini API key from https://aistudio.google.com/apikey
2. In Claude Desktop, click the gear icon next to the "Local" dropdown
3. In the "Environment variables" dialog, add:
   GEMINI_API_KEY=your_api_key_here
4. Click "Save changes"
"""


def get_api_key() -> str:
    """Get the Gemini API key from environment, with helpful error if missing."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(API_KEY_ERROR, file=sys.stderr)
        sys.exit(1)
    return api_key


def generate_image(
    prompt: str,
    output_path: str,
    model: str = "gemini-3.1-flash-image-preview",
    aspect_ratio: Optional[str] = None,
    image_size: Optional[str] = None,
) -> Optional[str]:
    """Generate an image from a text prompt.

    Args:
        prompt: Text description of the image to generate
        output_path: Path to save the generated image
        model: Gemini model to use
        aspect_ratio: Aspect ratio (1:1, 16:9, 9:16, etc.)
        image_size: Resolution (1K, 2K, 4K - 4K only for pro model)

    Returns:
        Any text response from the model, or None
    """
    api_key = get_api_key()
    client = genai.Client(api_key=api_key)

    # Build config
    config_kwargs = {"response_modalities": ["TEXT", "IMAGE"]}

    image_config_kwargs = {}
    if aspect_ratio:
        image_config_kwargs["aspect_ratio"] = aspect_ratio
    if image_size:
        image_config_kwargs["image_size"] = image_size

    if image_config_kwargs:
        config_kwargs["image_config"] = types.ImageConfig(**image_config_kwargs)

    config = types.GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=config,
    )

    text_response = None
    image_saved = False

    for part in response.parts:
        if part.text is not None:
            text_response = part.text
        elif part.inline_data is not None:
            image = part.as_image()
            image.save(output_path)
            image_saved = True

    if not image_saved:
        raise RuntimeError("No image was generated. Check your prompt and try again.")

    return text_response


def main():
    parser = argparse.ArgumentParser(
        description="Generate images from text prompts using Gemini API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("prompt", help="Text prompt describing the image")
    parser.add_argument("output", help="Output file path (e.g., output.png)")
    parser.add_argument(
        "--model", "-m",
        default="gemini-3.1-flash-image-preview",
        choices=["gemini-3.1-flash-image-preview", "gemini-2.5-flash-image", "gemini-3-pro-image-preview"],
        help="Model to use (default: gemini-3.1-flash-image-preview)"
    )
    parser.add_argument(
        "--aspect", "-a",
        choices=["1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"],
        help="Aspect ratio"
    )
    parser.add_argument(
        "--size", "-s",
        choices=["512", "1K", "2K", "4K"],
        help="Image resolution (4K only with pro, 512 only with 3.1 flash)"
    )

    args = parser.parse_args()

    try:
        text = generate_image(
            prompt=args.prompt,
            output_path=args.output,
            model=args.model,
            aspect_ratio=args.aspect,
            image_size=args.size,
        )

        print(f"Image saved to: {args.output}")
        if text:
            print(f"Model response: {text}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
