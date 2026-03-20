#!/usr/bin/env python3
"""
Get a second opinion from Gemini on any task.

Usage:
    python3 gemini_think.py "Your question or prompt here"
    python3 gemini_think.py --file context.txt "What do you think about this approach?"
    python3 gemini_think.py --model gemini-2.5-flash "Quick question here"

Environment:
    GEMINI_API_KEY - Required (set via shell environment or Claude Desktop)
"""

import argparse
import os
import sys
from typing import Optional

from google import genai
from google.genai import types


API_KEY_ERROR = """
GEMINI_API_KEY environment variable not set.

To configure:
1. Get your Gemini API key from https://aistudio.google.com/apikey
2. Add to your shell profile (~/.zshrc):
   export GEMINI_API_KEY=your_api_key_here
3. Run: source ~/.zshrc
"""


def get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(API_KEY_ERROR, file=sys.stderr)
        sys.exit(1)
    return api_key


def ask_gemini(
    prompt: str,
    model: str = "gemini-3-pro-preview",
    context_file: Optional[str] = None,
    system_instruction: Optional[str] = None,
    thinking_budget: int = 8192,
) -> str:
    """Send a prompt to Gemini and return the text response.

    Args:
        prompt: The question or task to send
        model: Gemini model to use
        context_file: Optional file to include as context
        system_instruction: Optional system instruction
        thinking_budget: Max thinking tokens (0-8192, default 8192 = max)

    Returns:
        The model's text response
    """
    client = genai.Client(api_key=get_api_key())

    contents = []

    if context_file:
        if not os.path.exists(context_file):
            raise FileNotFoundError(f"Context file not found: {context_file}")
        with open(context_file, "r") as f:
            file_content = f.read()
        contents.append(f"<context>\n{file_content}\n</context>\n\n{prompt}")
    else:
        contents.append(prompt)

    config_kwargs = {
        "response_modalities": ["TEXT"],
        "thinking_config": types.ThinkingConfig(thinking_budget=thinking_budget),
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    config = types.GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    text = ""
    for part in response.parts:
        if part.text:
            text += part.text

    if not text:
        raise RuntimeError("No response from Gemini.")

    return text


def main():
    parser = argparse.ArgumentParser(
        description="Get a second opinion from Gemini",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("prompt", help="The question or task to send to Gemini")
    parser.add_argument(
        "--model", "-m",
        default="gemini-3-pro-preview",
        choices=["gemini-3-pro-preview", "gemini-3-flash-preview"],
        help="Model to use (default: gemini-3-pro-preview)",
    )
    parser.add_argument(
        "--file", "-f",
        dest="context_file",
        help="File to include as context",
    )
    parser.add_argument(
        "--system", "-s",
        dest="system_instruction",
        help="System instruction for the model",
    )
    parser.add_argument(
        "--thinking-budget", "-t",
        type=int,
        default=8192,
        help="Max thinking tokens (0-8192, default: 8192 = maximum reasoning depth)",
    )

    args = parser.parse_args()

    try:
        response = ask_gemini(
            prompt=args.prompt,
            model=args.model,
            context_file=args.context_file,
            system_instruction=args.system_instruction,
            thinking_budget=args.thinking_budget,
        )
        print(response)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
