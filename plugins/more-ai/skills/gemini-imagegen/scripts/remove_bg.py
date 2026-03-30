#!/usr/bin/env python3
"""
Remove background from images using macOS Shortcuts.
Uses Apple's built-in "Remove Background" action via the Shortcuts app.

SETUP (one-time):
    1. Open Shortcuts.app
    2. Create new shortcut named "Remove Background"
    3. Add "Receive input from" action at the top (accepts Images)
    4. Add "Remove background from" action, set input to "Shortcut Input"
    5. Add "Stop and output" action, set to output "Image Without Background"
    6. Save

    The shortcut flow should be:
        [Receive Images] → [Remove background from Shortcut Input] → [Stop and output Image Without Background]

Usage:
    python remove_bg.py input.jpg output.png
    python remove_bg.py input.jpg  # outputs to input_nobg.png (same folder)
"""

import subprocess
import sys
import os

SHORTCUT_NAME = "Remove Background"


def check_shortcut_exists() -> bool:
    """Check if the Remove Background shortcut exists."""
    result = subprocess.run(
        ["shortcuts", "list"], capture_output=True, text=True
    )
    return SHORTCUT_NAME in result.stdout


def remove_background(input_path: str, output_path: str) -> bool:
    """Remove background using macOS Shortcuts."""
    result = subprocess.run(
        ["shortcuts", "run", SHORTCUT_NAME, "-i", input_path, "-o", output_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if result.stderr:
            print(f"Error: {result.stderr}", file=sys.stderr)
        return False
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python remove_bg.py input.jpg [output.png]")
        sys.exit(1)

    input_path = os.path.abspath(sys.argv[1])

    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = os.path.abspath(sys.argv[2])
    else:
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}_nobg.png"

    # Check if shortcut exists
    if not check_shortcut_exists():
        print(f"Error: Shortcut '{SHORTCUT_NAME}' not found.")
        print()
        print("Setup (one-time):")
        print("  1. Open Shortcuts.app")
        print(f"  2. Create new shortcut named '{SHORTCUT_NAME}'")
        print("  3. Add 'Receive input from' action (accepts Images)")
        print("  4. Add 'Remove background from' action, set to 'Shortcut Input'")
        print("  5. Add 'Stop and output' action, output 'Image Without Background'")
        print("  6. Save")
        sys.exit(1)

    if remove_background(input_path, output_path):
        print(f"Saved: {output_path}")
    else:
        print("Failed to remove background")
        sys.exit(1)


if __name__ == "__main__":
    main()
