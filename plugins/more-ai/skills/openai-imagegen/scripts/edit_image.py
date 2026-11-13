#!/usr/bin/env python3
"""
Edit images using OpenAI's GPT-Image-2.6 (Sunburst or Flare).

Usage:
    python3 edit_image.py "instruction" output.png --image input.png [options]

Examples:
    python3 edit_image.py "Add a rainbow in the sky" edited.png --image photo.png
    python3 edit_image.py "Replace the background with a beach" out.png --image portrait.png --mask mask.png
    python3 edit_image.py "Recolor the circled vase cobalt blue; remove the red circle" out.png --image room.png --markup overlay.png
    python3 edit_image.py "Create a gift basket with these items" basket.png --image item1.png --image item2.png
    python3 edit_image.py "Make the flag wave in the wind" flag.gif --image flag.png

The output format follows the file extension unless --format is given.

Environment:
    OPENAI_API_KEY - Required
"""

import argparse
import sys

from openai_images import (
    BACKGROUNDS,
    COMPLEXITIES,
    EDIT_FORMATS,
    QUALITIES,
    OpenAIImageGenerator,
)


def main():
    parser = argparse.ArgumentParser(
        description="Edit images with OpenAI GPT-Image-2.6",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("instruction", help="Edit instruction")
    parser.add_argument("output", help="Output file path")
    parser.add_argument(
        "--image", "-i",
        action="append",
        required=True,
        help="Input image(s). Can specify multiple times; extra images act as references.",
    )
    parser.add_argument(
        "--mask", "-m",
        default=None,
        help="Mask image for inpainting (must have alpha channel, same size as the first input)",
    )
    parser.add_argument(
        "--markup",
        default=None,
        help="Transparent PNG annotation layer (circles, arrows, notes) the same size as the "
             "first input. Do not flatten it onto the image. Cannot be combined with --mask.",
    )
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
        help="Planning effort before rendering (API default: high). "
             "Lower it when an edit changes more than you asked for.",
    )
    parser.add_argument(
        "--size", "-s",
        default="auto",
        help="Output size as WxH (default: auto)",
    )
    parser.add_argument(
        "--format", "-f",
        default=None,
        choices=EDIT_FORMATS,
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

    args = parser.parse_args()

    try:
        gen = OpenAIImageGenerator()
        paths = gen.edit(
            images=args.image,
            instruction=args.instruction,
            output=args.output,
            model=args.model,
            mask=args.mask,
            markup=args.markup,
            quality=args.quality,
            size=args.size,
            output_format=args.format,
            output_compression=args.compression,
            complexity=args.complexity,
            background=args.background,
            frame_count=args.frames,
            frame_duration_ms=args.frame_ms,
        )

        for p in paths:
            print(f"Image saved to: {p}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
