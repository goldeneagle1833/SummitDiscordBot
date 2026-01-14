#!/usr/bin/env python3
"""Convert FAQ CSV to a well-formatted markdown document."""

import csv
import re
from pathlib import Path
from collections import defaultdict


def clean_text(text):
    """Clean up text formatting and handle special characters."""
    if not text:
        return ""

    # Replace double brackets with single brackets for links
    text = re.sub(r"\[\[([^\]]+)\]\]", r"[\1]", text)

    # Clean up extra whitespace while preserving paragraph breaks
    text = re.sub(r"\s+", " ", text).strip()

    return text


def convert_faq_to_markdown():
    """Convert the FAQ CSV to markdown format."""

    # Find the FAQ CSV file (it has a timestamp in the name)
    data_dir = Path(__file__).parent.parent / "data"
    faq_files = list(data_dir.glob("faq-*.csv"))

    if not faq_files:
        print("Error: No FAQ CSV file found!")
        return

    # Use the most recent file
    csv_path = max(faq_files, key=lambda p: p.stat().st_mtime)
    output_path = Path(__file__).parent.parent / "knowledge_base" / "rules" / "faq.md"

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Start building the markdown document
    markdown = """# Sorcery: Contested Realm - Frequently Asked Questions

This document contains official and community-sourced answers to frequently asked questions about specific cards in Sorcery: Contested Realm.

---

"""

    # Read and group FAQs by card
    card_faqs = defaultdict(list)

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        current_card = None

        for row in reader:
            card_name = row["card name"].strip()
            question = clean_text(row["question"])
            answer = clean_text(row["answer"])

            # Skip empty rows
            if not question and not answer:
                continue

            # If this row has a card name, update current card
            if card_name:
                current_card = card_name

            # Add the Q&A to the current card
            if current_card and question and answer:
                card_faqs[current_card].append({"question": question, "answer": answer})

    # Sort cards alphabetically
    sorted_cards = sorted(card_faqs.keys())

    # Build the markdown content
    for card_name in sorted_cards:
        markdown += f"\n## {card_name}\n\n"

        faqs = card_faqs[card_name]

        if len(faqs) == 1:
            # Single Q&A - simpler format
            markdown += f"**Q:** {faqs[0]['question']}\n\n"
            markdown += f"**A:** {faqs[0]['answer']}\n\n"
        else:
            # Multiple Q&As - numbered format
            for i, faq in enumerate(faqs, 1):
                markdown += f"**Q{i}:** {faq['question']}\n\n"
                markdown += f"**A{i}:** {faq['answer']}\n\n"

        markdown += "---\n"

    # Write the markdown file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"✓ Successfully converted FAQ to markdown!")
    print(f"  Input:  {csv_path.name}")
    print(f"  Output: {output_path}")
    print(f"  Cards: {len(sorted_cards)}")
    print(f"  Total Q&As: {sum(len(faqs) for faqs in card_faqs.values())}")
    print(f"  Size: {len(markdown):,} characters")


if __name__ == "__main__":
    convert_faq_to_markdown()
