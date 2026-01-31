"""Formatting utilities."""

import re
import hashlib

from webapp_config import EVENT_NAME_MAPPINGS


def format_event_name(folder_name: str) -> str:
    """Format event folder name into a readable display name."""
    if folder_name in EVENT_NAME_MAPPINGS:
        return EVENT_NAME_MAPPINGS[folder_name]
    return folder_name.replace("_", " ").replace("-", " ").title()


def extract_year_from_name(name: str) -> int:
    """Extract year from event name for sorting. Returns 0 if no year found."""
    # Look for 4-digit years (2020-2029)
    match = re.search(r"20(2[0-9])", name)
    if match:
        return int("20" + match.group(1))
    # Check for 2-digit years like "25" that likely mean 2025
    match = re.search(r"(?<!\d)(2[3-9])(?!\d)", name)
    if match:
        return int("20" + match.group(1))
    return 0


def generate_pseudonym(player_id) -> str:
    """Generate a consistent fun pseudonym from a player ID."""
    adjectives = [
        "Magical", "Sneaky", "Brave", "Silly", "Grumpy", "Happy", "Sleepy",
        "Dancing", "Flying", "Jumping", "Mystical", "Crafty", "Clever", "Dizzy",
        "Wobbly", "Bouncy", "Sparkly", "Fuzzy", "Quirky", "Jolly", "Wacky",
        "Zany", "Goofy", "Perky", "Spicy", "Frosty", "Fiery", "Stormy", "Sunny",
        "Breezy", "Shadowy", "Glowing", "Tiny", "Giant", "Swift", "Lazy",
        "Eager", "Shy", "Bold", "Wild", "Gentle", "Fierce", "Peaceful",
        "Chaotic", "Lucky", "Clumsy", "Graceful", "Daring",
    ]

    nouns = [
        "Wizard", "Dragon", "Penguin", "Unicorn", "Potato", "Banana", "Taco",
        "Ninja", "Pirate", "Robot", "Ghost", "Phoenix", "Turtle", "Narwhal",
        "Pancake", "Wombat", "Llama", "Koala", "Goblin", "Sphinx", "Kraken",
        "Yeti", "Mermaid", "Centaur", "Griffin", "Chimera", "Troll", "Dwarf",
        "Elf", "Fairy", "Gnome", "Ogre", "Badger", "Otter", "Panda", "Sloth",
        "Walrus", "Moose", "Raccoon", "Squirrel", "Platypus", "Axolotl",
        "Capybara", "Hedgehog", "Mango", "Coconut", "Pickle", "Waffle",
    ]

    hash_obj = hashlib.md5(str(player_id).encode())
    hash_int = int(hash_obj.hexdigest(), 16)

    adj_index = hash_int % len(adjectives)
    noun_index = (hash_int // len(adjectives)) % len(nouns)

    return f"{adjectives[adj_index]} {nouns[noun_index]}"
