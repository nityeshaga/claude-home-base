"""
OpenAI Image Generation Library (GPT-Image-2.6: Sunburst and Flare)

Usage:
    from openai_images import OpenAIImageGenerator

    gen = OpenAIImageGenerator()
    gen.generate("A sunset over mountains", "sunset.png")
    gen.generate("A cat blinking", "cat.gif", frame_count=8)
    gen.edit(["input.png"], "Add clouds", "output.png")
    gen.edit(["room.png"], "Recolor the circled vase blue", "out.png", markup="overlay.png")

Environment:
    OPENAI_API_KEY - Required

Needs openai>=3.50 (complexity, markup, gif and svg arrived with the 2.6 models).
"""

import base64
import os
import sys
from pathlib import Path
from typing import Optional

from openai import OpenAI


MODELS = {
    "sunburst": "gpt-image-2.6-sunburst",  # detailed work — the default
    "flare": "gpt-image-2.6-flare",  # fast iteration
}
DEFAULT_MODEL = "sunburst"

# SVG output is drawn by a text model working from a reference image the image
# model makes. The API requires naming that author model.
SVG_AUTHOR_MODEL = "gpt-6.1-sol"

PRESETS = {
    "draft": {"model": "flare", "quality": "low", "size": "1024x1024", "output_format": "jpeg"},
    "social": {"quality": "medium", "size": "1088x1088", "output_format": "png"},
    "print": {"quality": "medium", "size": "2048x2048", "output_format": "png"},
    "wide": {"quality": "medium", "size": "1920x1088", "output_format": "png"},
    "portrait": {"quality": "medium", "size": "1088x1920", "output_format": "png"},
}

QUALITIES = ["low", "medium", "high", "xhigh", "max", "auto"]
COMPLEXITIES = ["low", "medium", "high"]
BACKGROUNDS = ["transparent", "opaque", "auto"]
GENERATE_FORMATS = ["png", "jpeg", "webp", "gif", "svg"]
EDIT_FORMATS = ["png", "jpeg", "webp", "gif"]

_EXTENSION_FORMATS = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".webp": "webp",
    ".gif": "gif",
    ".svg": "svg",
}


def get_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return api_key


def resolve_model(model: Optional[str]) -> str:
    """Accepts 'sunburst', 'flare', or any full model ID."""
    model = model or DEFAULT_MODEL
    return MODELS.get(model, model)


def resolve_format(output: Path, output_format: Optional[str]) -> str:
    """An explicit format wins; otherwise the output file's extension decides."""
    return output_format or _EXTENSION_FORMATS.get(output.suffix.lower(), "png")


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


def _save(result, output: Path, output_format: str) -> list[Path]:
    saved = []
    many = len(result.data) > 1
    for i, image_data in enumerate(result.data):
        if many:
            suffix = output.suffix or f".{output_format}"
            path = output.parent / f"{output.stem}_{i+1}{suffix}"
        else:
            path = output
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(image_data.b64_json))
        saved.append(path)
    return saved


class OpenAIImageGenerator:

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or get_api_key())

    def generate(
        self,
        prompt: str,
        output: str | Path,
        *,
        model: Optional[str] = None,
        quality: str = "medium",
        size: str = "auto",
        output_format: Optional[str] = None,
        output_compression: Optional[int] = None,
        n: int = 1,
        preset: Optional[str] = None,
        complexity: Optional[str] = None,
        background: Optional[str] = None,
        frame_count: Optional[int] = None,
        frame_duration_ms: Optional[int] = None,
        svg_model: Optional[str] = None,
    ) -> list[Path]:
        output = Path(output)

        if preset and preset in PRESETS:
            defaults = PRESETS[preset]
            quality = defaults["quality"]
            size = defaults["size"]
            output_format = defaults["output_format"]
            model = model or defaults.get("model")

        output_format = resolve_format(output, output_format)

        kwargs = {
            "model": resolve_model(model),
            "prompt": prompt,
            "n": n,
            "quality": quality,
            "size": _normalize_size(size),
        }
        if output_format != "png":
            kwargs["output_format"] = output_format
        if output_compression is not None:
            kwargs["output_compression"] = output_compression
        if complexity:
            kwargs["complexity"] = complexity
        if background:
            kwargs["background"] = background
        if frame_count is not None:
            kwargs["frame_count"] = frame_count
        if frame_duration_ms is not None:
            kwargs["frame_duration_ms"] = frame_duration_ms
        if output_format == "svg":
            kwargs["svg"] = {"model": svg_model or SVG_AUTHOR_MODEL}

        result = self.client.images.generate(**kwargs)
        return _save(result, output, output_format)

    def edit(
        self,
        images: list[str | Path],
        instruction: str,
        output: str | Path,
        *,
        model: Optional[str] = None,
        mask: Optional[str | Path] = None,
        markup: Optional[str | Path] = None,
        quality: str = "medium",
        size: str = "auto",
        output_format: Optional[str] = None,
        output_compression: Optional[int] = None,
        complexity: Optional[str] = None,
        background: Optional[str] = None,
        frame_count: Optional[int] = None,
        frame_duration_ms: Optional[int] = None,
    ) -> list[Path]:
        output = Path(output)
        output_format = resolve_format(output, output_format)

        if mask and markup:
            raise ValueError("Use --mask or --markup, not both.")

        files = [open(str(img), "rb") for img in images]
        kwargs = {
            "model": resolve_model(model),
            "image": files if len(files) > 1 else files[0],
            "prompt": instruction,
            "quality": quality,
            "size": _normalize_size(size),
        }
        if output_format != "png":
            kwargs["output_format"] = output_format
        if output_compression is not None:
            kwargs["output_compression"] = output_compression
        if complexity:
            kwargs["complexity"] = complexity
        if background:
            kwargs["background"] = background
        if frame_count is not None:
            kwargs["frame_count"] = frame_count
        if frame_duration_ms is not None:
            kwargs["frame_duration_ms"] = frame_duration_ms
        if mask:
            kwargs["mask"] = open(str(mask), "rb")
            files.append(kwargs["mask"])
        if markup:
            kwargs["markup"] = open(str(markup), "rb")
            files.append(kwargs["markup"])

        try:
            result = self.client.images.edit(**kwargs)
        finally:
            for f in files:
                f.close()

        return _save(result, output, output_format)
