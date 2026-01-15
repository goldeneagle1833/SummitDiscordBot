"""
Script to convert All_Cards_Array.json to markdown for the knowledge base.
This creates a searchable card database for the AI.
"""

import sys
from pathlib import Path
import json

# Paths
CARDS_JSON = Path(__file__).parent.parent.parent / "web-app" / "curiosa-io-tools" / "All_Cards_Array.json"
OUTPUT_DIR = Path(__file__).parent.parent / "knowledge_base" / "card_rulings"


def format_thresholds(thresholds):
    """Format threshold requirements."""
    if not thresholds:
        return "None"
    
    elements = []
    for element, count in thresholds.items():
        if count > 0:
            elements.append(f"{element.capitalize()}: {count}")
    
    return ", ".join(elements) if elements else "None"


def convert_cards():
    """Convert cards JSON to markdown files."""
    print(f"Loading cards from {CARDS_JSON}...")
    
    with open(CARDS_JSON, "r", encoding="utf-8") as f:
        cards = json.load(f)
    
    print(f"Found {len(cards)} cards")
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Build markdown content - group by type for better organization
    cards_by_type = {}
    
    for card in cards:
        name = card.get("name", "Unknown")
        guardian = card.get("guardian", {})
        
        if not guardian:
            continue
            
        card_type = guardian.get("type", "Unknown")
        
        if card_type not in cards_by_type:
            cards_by_type[card_type] = []
        
        # Build card entry
        entry = {
            "name": name,
            "type": card_type,
            "rarity": guardian.get("rarity", "Unknown"),
            "cost": guardian.get("cost"),
            "rules_text": guardian.get("rulesText", ""),
            "attack": guardian.get("attack"),
            "defence": guardian.get("defence"),
            "life": guardian.get("life"),
            "thresholds": guardian.get("thresholds", {}),
            "elements": card.get("elements", "None"),
            "subtypes": card.get("subTypes", ""),
            "sets": [s.get("name", "") for s in card.get("sets", [])]
        }
        
        cards_by_type[card_type].append(entry)
    
    # Create one file per card type
    for card_type, type_cards in cards_by_type.items():
        filename = f"{card_type.lower().replace(' ', '_')}_cards.md"
        filepath = OUTPUT_DIR / filename
        
        content = f"# {card_type} Cards\n\n"
        content += f"This document contains all {card_type} cards in Sorcery: Contested Realm.\n\n"
        
        for card in sorted(type_cards, key=lambda x: x["name"]):
            content += f"## {card['name']}\n\n"
            content += f"**Type:** {card['type']}\n"
            content += f"**Rarity:** {card['rarity']}\n"
            
            if card['cost'] is not None:
                content += f"**Cost:** {card['cost']}\n"
            
            if card['subtypes']:
                content += f"**Subtypes:** {card['subtypes']}\n"
            
            content += f"**Elements:** {card['elements']}\n"
            content += f"**Thresholds:** {format_thresholds(card['thresholds'])}\n"
            
            if card['attack'] is not None or card['defence'] is not None:
                content += f"**Attack/Defence:** {card['attack'] or '-'}/{card['defence'] or '-'}\n"
            
            if card['life'] is not None:
                content += f"**Life:** {card['life']}\n"
            
            if card['rules_text']:
                content += f"\n**Rules Text:** {card['rules_text']}\n"
            
            if card['sets']:
                content += f"\n**Available in:** {', '.join(card['sets'])}\n"
            
            content += "\n---\n\n"
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"Created {filepath.name} with {len(type_cards)} cards")
    
    # Also create a master cards file with all cards for quick reference
    master_file = OUTPUT_DIR / "all_cards_reference.md"
    master_content = "# Sorcery: Contested Realm - Complete Card Reference\n\n"
    master_content += "This is a quick reference of all cards in the game.\n\n"
    
    for card in sorted(cards, key=lambda x: x.get("name", "")):
        name = card.get("name", "Unknown")
        guardian = card.get("guardian", {})
        
        if not guardian:
            continue
        
        rules_text = guardian.get("rulesText", "No rules text")
        card_type = guardian.get("type", "Unknown")
        cost = guardian.get("cost", "?")
        
        master_content += f"**{name}** ({card_type}, Cost {cost}): {rules_text}\n\n"
    
    with open(master_file, "w", encoding="utf-8") as f:
        f.write(master_content)
    
    print(f"\nCreated master reference file: {master_file.name}")
    print(f"\nTotal files created: {len(cards_by_type) + 1}")
    print("\nDone! Re-run the knowledge base indexer to include these cards.")


if __name__ == "__main__":
    convert_cards()
