#!/usr/bin/env python3
"""
Generate images from text prompts using OpenAI's GPT-Image-2.6 (Sunburst or Flare).

Usage:
    python3 generate_image.py "prompt" output.png [options]

Examples:
    python3 generate_image.py "A cat in space" cat.png
    python3 generate_image.py "Marketing banner for AI consulting" banner.png --preset wide
    python3 generate_image.py "Infographic about Q4 results" info.png --quality high --size 2048x2048
    python3 generate_image.py "Rough thumbnail ideas" idea.jpg --model flare --quality low
    python3 generate_image.py "A paper plane looping" plane.gif --frames 12 --frame-ms 100
    python3 generate_image.py "Minimal fox logo, flat shapes" fox.svg
    python3 generate_image.py "Sticker of a smiling sun" sun.png --background transparent

The output format follows the file extension unless --format is given.

Environment:
    OPENAI_API_KEY - Required
"""

import argparse
import sys

from openai_images import (
    BACKGROUNDS,
    COMPLEXITIES,
    GENERATE_FORMATS,
    PRESETS,
    QUALITIES,
    SVG_AUTHOR_MODEL,
    OpenAIImageGenerator,
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate images with OpenAI GPT-Image-2.6",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("prompt", help="Text prompt describing the image")
    parser.add_argument("output", help="Output file path (e.g., output.png)")
    parser.add_argument(
        "--model",
        default=None,
        help="'sunburst' (detailed, default), 'flare' (fast), or a full model ID",
    )
    parser.add_argument(
        "--quality", "-q",
        default="medium",
        choices=QUALITIES,
        help="Rendering quality (default: medium)",
    )
    parser.add_argument(
        "--complexity",
        default=None,
        choices=COMPLEXITIES,
        help="Planning effort before rendering (API default: high)",
    )
    parser.add_argument(
        "--size", "-s",
        default="auto",
        help="Image size as WxH (multiples of 16, max 3840x2160). Or 'auto' (default: auto)",
    )
    parser.add_argument(
        "--format", "-f",
        default=None,
        choices=GENERATE_FORMATS,
        help="Output format (default: from the output file extension, else png)",
    )
    parser.add_argument(
        "--compression",
        type=int,
        default=None,
        help="Compression level 0-100 for jpeg/webp",
    )
    parser.add_argument(
        "--background",
        default=None,
        choices=BACKGROUNDS,
        help="'transparent' needs png or webp",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        help="GIF only: number of frames, 2-16 (API default: 9)",
    )
    parser.add_argument(
        "--frame-ms",
        type=int,
        default=None,
        help="GIF only: delay per frame in milliseconds (API default: 200)",
    )
    parser.add_argument(
        "--svg-model",
        default=None,
        help=f"SVG only: text model that authors the SVG (default: {SVG_AUTHOR_MODEL})",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="Number of images to generate (1-10, default: 1; svg needs 1)",
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
            model=args.model,
            quality=args.quality,
            size=args.size,
            output_format=args.format,
            output_compression=args.compression,
            n=args.n,
            preset=args.preset,
            complexity=args.complexity,
            background=args.background,
            frame_count=args.frames,
            frame_duration_ms=args.frame_ms,
            svg_model=args.svg_model,
        )

        for p in paths:
            print(f"Image saved to: {p}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
