#!/usr/bin/env python3
"""
Generate images from text prompts using OpenAI's gpt-image-2.

Usage:
    python3 generate_image.py "prompt" output.png [options]

Examples:
    python3 generate_image.py "A cat in space" cat.png
    python3 generate_image.py "Marketing banner for AI consulting" banner.png --preset wide
    python3 generate_image.py "Infographic about Q4 results" info.png --quality high --size 2048x2048

Environment:
    OPENAI_API_KEY - Required
"""

import argparse
import sys

from openai_images import OpenAIImageGenerator, PRESETS


def main():
    parser = argparse.ArgumentParser(
        description="Generate images with OpenAI gpt-image-2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("prompt", help="Text prompt describing the image")
    parser.add_argument("output", help="Output file path (e.g., output.png)")
    parser.add_argument(
        "--quality", "-q",
        default="medium",
        choices=["low", "medium", "high", "auto"],
        help="Image quality (default: medium)",
    )
    parser.add_argument(
        "--size", "-s",
        default="auto",
        help="Image size as WxH (multiples of 16, max 3840). Or 'auto' (default: auto)",
    )
    parser.add_argument(
        "--format", "-f",
        default="png",
        choices=["png", "jpeg", "webp"],
        help="Output format (default: png)",
    )
    parser.add_argument(
        "--compression",
        type=int,
        default=None,
        help="Compression level 0-100 for jpeg/webp",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="Number of images to generate (1-8, default: 1)",
    )
    parser.add_argument(
        "--preset", "-p",
        choices=list(PRESETS.keys()),
        help="Quality preset (overrides quality/size/format)",
    )

    args = parser.parse_args()

    try:
        gen = OpenAIImageGenerator()
        paths = gen.generate(
            prompt=args.prompt,
            output=args.output,
            quality=args.quality,
            size=args.size,
            output_format=args.format,
            output_compression=args.compression,
            n=args.n,
            preset=args.preset,
        )

        for p in paths:
            print(f"Image saved to: {p}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
