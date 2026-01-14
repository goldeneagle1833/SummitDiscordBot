#!/usr/bin/env python3
"""
Format quick start rules with proper markdown headers.
This version works by identifying standalone section titles.
"""

from pathlib import Path
import re


def format_quick_start_rules():
    """Format the quick start rules with proper markdown structure."""

    input_path = (
        Path(__file__).parent.parent
        / "knowledge_base"
        / "rules"
        / "quick_start_rules.md"
    )

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Remove any existing formatting from previous runsdfzg
    # Remove lines that are just "###" followed by partial sentences
    content = re.sub(r"^### [A-Z][^\n]*?(?=\n\n[a-z])", "", content, flags=re.MULTILINE)

    # Define exact section titles that should be headers
    major_sections = [
        "Introduction",
        "The Four Elements",
        "Card Types",
        "Game Zones",
        "Navigating the Realm",
        "Turn Summary",
        "Casting Spells",
        "Activating Abilities",
        "Basic Abilities",
        "Building Your Own Decks",
        "Advanced Concepts",
        "Glossary of Terms",
        "Quick Reference Guide",
    ]

    minor_sections = [
        "Using this Rulebook",
        "Gameplay",
        "How to Win",
        "Decks",
        "Air",
        "Earth",
        "Fire",
        "Water",
        "Cards",
        "The Golden Rule",
        "Avatars",
        "Sites",
        "Spells",
        "Minions",
        "Artifacts",
        "Monuments",
        "Automatons",
        "Auras",
        "Magics",
        "The Realm",
        "Atlas and Spellbook Decks",
        "Cemetery",
        "Hand",
        "Setup",
        "Winning the Game",
        "Death's Door",
        "Death Blow",
        "Areas of the Realm",
        "Squares",
        "The Void",
        "Bodies of Water",
        "Land",
        "Surface",
        "Subsurface",
        "Regions",
        "Locating Areas",
        "Location",
        "Adjacent",
        "Nearby",
        "Steps",
        "Start Phase",
        "Main Phase",
        "End Phase",
        "Mana",
        "Elemental Threshold",
        "Casting Minions",
        "Casting Artifacts",
        "Casting Auras",
        "Casting Magics",
        "Tapping a Card",
        "Playing Sites",
        "Move & Attack",
        "Move and Attack",
        "Attacking the Enemy",
        "Defend",
        "Intercept",
        "Pick Up or Drop Artifacts",
        "Special Abilities",
        "Advanced Movement Concepts",
        "Damage Grids",
        "Occupying Multiple Sites",
        "Ownership and Control",
        "Projectiles",
        "Static/Ongoing Effects",
        "The Storyline",
        "Common Keyword Abilities",
    ]

    # Find "Rulebook released December 2025" and remove everything before it from the body
    # (keep the initial header we want)
    marker = "Rulebook released December 2025"
    marker_pos = content.find(marker)

    if marker_pos > 100:  # Make sure we found it and it's not at the very start
        # Keep the header part (before marker)
        header_part = content[:marker_pos]
        # Get the content after marker
        body_part = content[marker_pos + len(marker) :]

        # Clean up header if it has duplicate info
        if "For more detailed rules" in header_part:
            # We have our formatted header already, just start from there
            lines = header_part.split("\n")
            # Find the "---" separator
            sep_idx = -1
            for i, line in enumerate(lines):
                if line.strip() == "---":
                    sep_idx = i
                    break

            if sep_idx > 0:
                header_part = "\n".join(
                    lines[: sep_idx + 2]
                )  # Include --- and blank line

        content = header_part + body_part

    # Now format section headers
    # For major sections: ## Header
    for section in major_sections:
        # Match the section name on its own line (not part of a longer sentence)
        pattern = f"(?<=[\\n\\r])({re.escape(section)})(?=[\\n\\r])"
        content = re.sub(pattern, f"## {section}", content)

    # For minor sections: ### Header
    for section in minor_sections:
        # Only if not already a header
        pattern = f"(?<=[\\n\\r])(?!#)({re.escape(section)})(?=[\\n\\r])"
        content = re.sub(pattern, f"### {section}", content)

    # Replace page number markers (e.g., "- 3 -") with horizontal rules
    content = re.sub(r"^-\s*\d+\s*-\s*$", "---", content, flags=re.MULTILINE)

    # Clean up multiple empty lines
    content = re.sub(r"\n{3,}", "\n\n", content)

    # Write back
    with open(input_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✓ Successfully formatted quick start rules!")
    print(f"  File: {input_path}")
    print(f"  Size: {len(content):,} characters")
    print(f"  Lines: {len(content.splitlines())}")


if __name__ == "__main__":
    format_quick_start_rules()
