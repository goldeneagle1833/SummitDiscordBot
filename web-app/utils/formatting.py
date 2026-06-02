"""Formatting utilities."""

import re
import hashlib
from datetime import datetime

from webapp_config import EVENT_NAME_MAPPINGS

MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def format_event_name(folder_name: str) -> str:
    """Format event folder name into a readable display name."""
    if folder_name in EVENT_NAME_MAPPINGS:
        return EVENT_NAME_MAPPINGS[folder_name]
    return folder_name.replace("_", " ").replace("-", " ").title()


def extract_date_from_name(folder_name: str) -> str | None:
    """Extract ISO date (YYYY-MM-DD) from event folder name.

    Handles patterns like:
    - "Ascanrask III 2026 4 4" -> "2026-04-04"
    - "Assorted Animals Tournament Grounds 5_19_2026" -> "2026-05-19"
    - "Aus Store Championship 3 28 2026" -> "2026-03-28"
    - "Scgcon Richmond 3-9-2026" -> "2026-03-09"
    - "Sorcerers Summit Gothic Season 2 3-18-2026" -> "2026-03-18"
    - "LinCon May 14-16 2026" -> "2026-05-14"
    - "Battle of Elverson Fields May 23rd 2026" -> "2026-05-23"

    Returns None for unparseable names like "GenCon2024Stats".
    """
    name = folder_name.replace("_", " ")

    # Pattern: YYYY M D at end (e.g., "Ascanrask III 2026 4 4")
    m = re.search(r"(20\d{2})\s+(\d{1,2})\s+(\d{1,2})\s*$", name)
    if m:
        result = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result

    # Pattern: Month D-D YYYY or Month Drd/th/st YYYY (e.g., "May 14-16 2026", "May 23rd 2026")
    # Check this BEFORE M-D-YYYY to avoid "14-16 2026" being parsed as month=14
    m = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?(?:\s*-\s*\d{1,2}(?:st|nd|rd|th)?)?\s+(20\d{2})",
        name, re.IGNORECASE,
    )
    if m:
        month = MONTH_NAMES[m.group(1).lower()]
        result = _safe_date(int(m.group(3)), month, int(m.group(2)))
        if result:
            return result

    # Pattern: M-D-YYYY or M D YYYY at end (e.g., "3-9-2026", "3 28 2026")
    m = re.search(r"(\d{1,2})[\s-]+(\d{1,2})[\s-]+(20\d{2})\s*$", name)
    if m:
        result = _safe_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if result:
            return result

    return None


def _safe_date(year: int, month: int, day: int) -> str | None:
    """Build ISO date string, returning None if values are invalid."""
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def strip_date_from_name(name: str) -> str:
    """Remove date components from a display name.

    Examples:
    - "Ascanrask III 2026 4 4" -> "Ascanrask III"
    - "Battle Of Elverson Fields May 23Rd 2026" -> "Battle Of Elverson Fields"
    - "Scgcon Richmond 3 9 2026" -> "Scgcon Richmond"
    - "Sorcerers Summit Gothic Season 2 3 18 2026" -> "Sorcerers Summit Gothic Season 2"
    """
    result = name

    # Strip trailing YYYY M D
    result = re.sub(r"\s+20\d{2}\s+\d{1,2}\s+\d{1,2}\s*$", "", result)

    # Strip trailing Month D-D YYYY or Month Drd YYYY (before M-D-YYYY to handle "May 14 16 2026")
    result = re.sub(
        r"\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*[-\s]+\d{1,2}(?:st|nd|rd|th)?)?\s+20\d{2}\s*$",
        "", result, flags=re.IGNORECASE,
    )

    # Strip trailing M-D-YYYY or M D YYYY
    result = re.sub(r"\s+\d{1,2}[\s-]+\d{1,2}[\s-]+20\d{2}\s*$", "", result)

    # Strip trailing bare year if it's the only thing left after event name
    # Only if the name had more content before the year
    stripped_year = re.sub(r"\s+20\d{2}\s*$", "", result)
    if stripped_year and stripped_year != result:
        result = stripped_year

    return result.strip()


def format_date_display(iso_date: str | None, year: int | None = None) -> str | None:
    """Format an ISO date string to human-readable display.

    - "2026-04-04" -> "Apr 4, 2026"
    - None with year=2024 -> "2024"
    - None with year=None -> None
    """
    if iso_date:
        try:
            dt = datetime.strptime(iso_date, "%Y-%m-%d")
            # %#d on Windows, %-d on Linux/Mac — use manual formatting for portability
            return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
        except (ValueError, AttributeError):
            pass
        return iso_date
    if year and year > 0:
        return str(year)
    return None


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
