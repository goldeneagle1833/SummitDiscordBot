#!/usr/bin/env python3
"""Convert codex.csv to a well-formatted markdown document."""

import csv
import re
from pathlib import Path


def clean_text(text):
    """Clean up text formatting and handle special characters."""
    if not text:
        return ""

    # Replace double brackets with single brackets for links
    text = re.sub(r"\[\[([^\]]+)\]\]", r"[\1]", text)

    # Clean up extra whitespace while preserving paragraph breaks
    text = re.sub(r"\s+", " ", text).strip()

    return text


def convert_codex_to_markdown():
    """Convert the codex CSV to markdown format."""

    # File paths
    csv_path = Path(__file__).parent.parent / "data" / "codex.csv"
    output_path = Path(__file__).parent.parent / "knowledge_base" / "rules" / "codex.md"

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Start building the markdown document
    markdown = """# Sorcery: Contested Realm - Codex

This document contains definitions and explanations of game terms, mechanics, and card interactions for Sorcery: Contested Realm.

---

"""

    # Read and process the CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        current_title = None
        entry_count = 0

        for row in reader:
            title = row["title"].strip()
            content = clean_text(row["content"])
            subcodex = clean_text(row["subcodexes"])

            # Skip empty rows
            if not title and not content and not subcodex:
                continue

            # If this is a new entry (has a title)
            if title:
                current_title = title
                markdown += f"\n## {title}\n\n"

                if content:
                    markdown += f"{content}\n\n"

                if subcodex:
                    markdown += f"**Additional Details:**\n\n{subcodex}\n\n"

                entry_count += 1

            # If this is a continuation (no title, but has content or subcodex)
            elif content or subcodex:
                if content:
                    markdown += f"{content}\n\n"

                if subcodex:
                    markdown += f"**Additional Details:**\n\n{subcodex}\n\n"

    # Write the markdown file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"✓ Successfully converted codex to markdown!")
    print(f"  Input:  {csv_path}")
    print(f"  Output: {output_path}")
    print(f"  Entries: {entry_count}")
    print(f"  Size: {len(markdown):,} characters")


if __name__ == "__main__":
    convert_codex_to_markdown()
