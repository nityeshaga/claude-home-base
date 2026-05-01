"""
OpenAI Image Generation Library (gpt-image-2)

Usage:
    from openai_images import OpenAIImageGenerator

    gen = OpenAIImageGenerator()
    gen.generate("A sunset over mountains", "sunset.png")
    gen.edit(["input.png"], "Add clouds", "output.png")

Environment:
    OPENAI_API_KEY - Required
"""

import base64
import os
import re
import sys
from pathlib import Path
from typing import Optional

from openai import OpenAI


PRESETS = {
    "draft": {"quality": "low", "size": "1024x1024", "output_format": "jpeg"},
    "social": {"quality": "medium", "size": "1088x1088", "output_format": "png"},
    "print": {"quality": "medium", "size": "2048x2048", "output_format": "png"},
    "wide": {"quality": "medium", "size": "1920x1088", "output_format": "png"},
    "portrait": {"quality": "medium", "size": "1088x1920", "output_format": "png"},
}

MODEL = "gpt-image-2"


def get_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return api_key


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _snap_to_16(n: int) -> int:
    return max(16, (n + 8) // 16 * 16)


def _normalize_size(size: str) -> str:
    if size == "auto":
        return "auto"
    parts = size.lower().split("x")
    if len(parts) != 2:
        return size
    w, h = _snap_to_16(int(parts[0])), _snap_to_16(int(parts[1]))
    return f"{w}x{h}"


class OpenAIImageGenerator:

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or get_api_key())

    def generate(
        self,
        prompt: str,
        output: str | Path,
        *,
        quality: str = "medium",
        size: str = "auto",
        output_format: str = "png",
        output_compression: Optional[int] = None,
        n: int = 1,
        preset: Optional[str] = None,
    ) -> list[Path]:
        output = Path(output)

        if preset and preset in PRESETS:
            defaults = PRESETS[preset]
            quality = defaults["quality"]
            size = defaults["size"]
            output_format = defaults["output_format"]

        size = _normalize_size(size)

        kwargs = {
            "model": MODEL,
            "prompt": prompt,
            "n": n,
            "quality": quality,
            "size": size,
        }
        if output_format != "png":
            kwargs["output_format"] = output_format
        if output_compression is not None:
            kwargs["output_compression"] = output_compression

        result = self.client.images.generate(**kwargs)

        saved = []
        for i, image_data in enumerate(result.data):
            if n > 1:
                stem = output.stem
                suffix = output.suffix or f".{output_format}"
                path = output.parent / f"{stem}_{i+1}{suffix}"
            else:
                path = output

            image_bytes = base64.b64decode(image_data.b64_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            saved.append(path)

        return saved

    def edit(
        self,
        images: list[str | Path],
        instruction: str,
        output: str | Path,
        *,
        mask: Optional[str | Path] = None,
        quality: str = "medium",
        size: str = "auto",
        output_format: str = "png",
    ) -> list[Path]:
        output = Path(output)
        size = _normalize_size(size)

        image_files = [open(str(img), "rb") for img in images]

        kwargs = {
            "model": MODEL,
            "image": image_files if len(image_files) > 1 else image_files[0],
            "prompt": instruction,
            "quality": quality,
            "size": size,
        }

        if mask:
            kwargs["mask"] = open(str(mask), "rb")

        try:
            result = self.client.images.edit(**kwargs)
        finally:
            for f in image_files:
                f.close()
            if mask and "mask" in kwargs:
                kwargs["mask"].close()

        saved = []
        for i, image_data in enumerate(result.data):
            if len(result.data) > 1:
                stem = output.stem
                suffix = output.suffix or f".{output_format}"
                path = output.parent / f"{stem}_{i+1}{suffix}"
            else:
                path = output

            image_bytes = base64.b64decode(image_data.b64_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            saved.append(path)

        return saved
