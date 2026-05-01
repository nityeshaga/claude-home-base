#!/usr/bin/env python3
"""
Edit images using OpenAI's gpt-image-2.

Usage:
    python3 edit_image.py "instruction" output.png --image input.png [options]

Examples:
    python3 edit_image.py "Add a rainbow in the sky" edited.png --image photo.png
    python3 edit_image.py "Replace the background with a beach" out.png --image portrait.png --mask mask.png
    python3 edit_image.py "Create a gift basket with these items" basket.png --image item1.png --image item2.png

Environment:
    OPENAI_API_KEY - Required
"""

import argparse
import sys

from openai_images import OpenAIImageGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Edit images with OpenAI gpt-image-2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("instruction", help="Edit instruction")
    parser.add_argument("output", help="Output file path")
    parser.add_argument(
        "--image", "-i",
        action="append",
        required=True,
        help="Input image(s). Can specify multiple times for composition.",
    )
    parser.add_argument(
        "--mask", "-m",
        default=None,
        help="Mask image for inpainting (must have alpha channel, same size as input)",
    )
    parser.add_argument(
        "--quality", "-q",
        default="medium",
        choices=["low", "medium", "high", "auto"],
        help="Image quality (default: medium)",
    )
    parser.add_argument(
        "--size", "-s",
        default="auto",
        help="Output size as WxH (default: auto)",
    )
    parser.add_argument(
        "--format", "-f",
        default="png",
        choices=["png", "jpeg", "webp"],
        help="Output format (default: png)",
    )

    args = parser.parse_args()

    try:
        gen = OpenAIImageGenerator()
        paths = gen.edit(
            images=args.image,
            instruction=args.instruction,
            output=args.output,
            mask=args.mask,
            quality=args.quality,
            size=args.size,
            output_format=args.format,
        )

        for p in paths:
            print(f"Image saved to: {p}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
