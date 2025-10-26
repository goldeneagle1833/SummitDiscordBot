import requests
import json
import os


def get_deck_id(url: str) -> str:
    """Extract deck ID from Curiosa URL."""
    return url.rstrip("/").split("/")[-1]


def scrape_Curosa(deck_url, name):
    """Scrape deck data from Curiosa and save to file."""
    deck_id = get_deck_id(deck_url)
    response = requests.get("https://curiosa.io/api/decks?ids=" + deck_id)

    if response.status_code != 200:
        print(f"Failed to retrieve the website. Status code: {response.status_code}")
        return None

    json_data = json.loads(response.text)

    # Load existing data from file if it exists
    if os.path.exists(name):
        with open(name, "r") as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = []
    else:
        existing_data = []

    # Append the new data to existing data
    existing_data.append(json_data[0])

    # Write the updated data back to the file
    with open(name, "w") as f:
        json.dump(existing_data, f, indent=2)

    # Return json data as a string to save in the db
    json_data = json.dumps(json_data[0])
    return json_data


def search_deck(
    deck_data,
    card_name=None,
    min_quantity=None,
    max_quantity=None,
    card_type=None,
    element=None,
    rarity=None,
):
    """
    Search for cards in a deck with various filters.

    Parameters:
    - deck_data: The deck JSON data (list or dict)
    - card_name: Search for specific card by name (case-insensitive, partial match)
    - min_quantity: Find cards with at least this many copies
    - max_quantity: Find cards with at most this many copies
    - card_type: Filter by type (Minion, Magic, Artifact, Aura, Site, Avatar)
    - element: Filter by element (Earth, Water, Air, Fire, None)
    - rarity: Filter by rarity (Ordinary, Exceptional, Elite, Unique)

    Returns:
    - List of matching cards with their section and details
    """
    # Handle if deck_data is a list (extract first deck)
    if isinstance(deck_data, list):
        deck = deck_data[0]
    else:
        deck = deck_data

    results = []
    sections = ["avatar", "spellbook", "atlas", "sideboard"]

    for section in sections:
        if section not in deck or not deck[section]:
            continue

        for card in deck[section]:
            # Apply filters
            if card_name and card_name.lower() not in card["name"].lower():
                continue

            if min_quantity and card.get("quantity", 1) < min_quantity:
                continue

            if max_quantity and card.get("quantity", 1) > max_quantity:
                continue

            if card_type and card["type"] != card_type:
                continue

            if element and element not in card.get("elements", ""):
                continue

            if rarity and card["rarity"] != rarity:
                continue

            # Add matching card to results
            results.append(
                {
                    "section": section,
                    "name": card["name"],
                    "quantity": card.get("quantity", 1),
                    "type": card["type"],
                    "elements": card.get("elements", "None"),
                    "rarity": card["rarity"],
                    "cost": card.get("cost"),
                    "power": card.get("power"),
                    "keywords": card.get("keywords", ""),
                }
            )

    return results


def find_card(deck_data, card_name):
    """Quick search for a specific card by name."""
    return search_deck(deck_data, card_name=card_name)


def find_high_quantity_cards(deck_data, min_copies=3):
    """Find cards with many copies."""
    return search_deck(deck_data, min_quantity=min_copies)


def count_card_copies(deck_data, card_name):
    """Count how many copies of a card are in the deck."""
    results = search_deck(deck_data, card_name=card_name)
    return sum(card["quantity"] for card in results)
