#!/usr/bin/env python3
"""
PACE Rebrand Script
Run this script to apply all Hermes -> PACE replacements consistently.
"""

import os
import re
from pathlib import Path

REPLACEMENTS = [
    # Basic replacements
    (r"\bHermes\b", "PACE"),
    (r"\bhermes\b", "pace"),
    (r"\bHermes CLI\b", "PACE CLI"),
    (r"\bHermes Agent\b", "PACE Atlas"),
    (r"\bHermes Gateway\b", "PACE Gateway"),
    # Constants
    (r"\bHERMES_HOME\b", "PACE_HOME"),
    (r"\bhermes_cli\b", "pace_cli"),
    (r"\bhermes-agent\b", "pace-agent"),
    (r"~\.hermes", "~/.pace"),
    # Emoji and symbols
    (r"⚕", "⚡"),
    (r"⚔", "⚡"),
    # Comments and docstrings
    (r"Hermes —", "PACE —"),
    (r"Hermes system", "PACE system"),
    (r"Hermes installation", "PACE installation"),
    # Hardcoded paths
    (r"/\.hermes/", "/.pace/"),
]


def process_file(filepath: Path) -> int:
    """Apply all replacements to a file. Returns number of changes."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [SKIP] {filepath}: {e}")
        return 0

    original = content
    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)

    if content != original:
        filepath.write_text(content, encoding="utf-8")
        return 1
    return 0


def main():
    base = Path("/Users/sohamjadhav/hermes-agent")

    # Directories to process
    dirs = [
        base / "pace_cli",
        base / "prompts",
        base / "gateway",
    ]

    total = 0
    for d in dirs:
        if not d.exists():
            continue
        for py_file in d.rglob("*.py"):
            changes = process_file(py_file)
            if changes:
                print(f"  Updated: {py_file.relative_to(base)}")
                total += 1

    # Also process pyproject.toml
    toml = base / "pyproject.toml"
    if toml.exists():
        process_file(toml)
        print(f"  Updated: pyproject.toml")
        total += 1

    print(f"\nDone. Updated {total} files.")


if __name__ == "__main__":
    main()
