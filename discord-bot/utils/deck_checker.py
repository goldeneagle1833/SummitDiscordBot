import asyncio
import json
import os
import time
import requests
try:
    import certifi
    _REQUESTS_VERIFY = certifi.where()
    _SSL_CONTEXT = None  # aiohttp uses ssl.create_default_context() with certifi if available
except Exception:
    _REQUESTS_VERIFY = True
    _SSL_CONTEXT = None


def get_deck_id(url: str) -> str:
    """Extract deck ID from Curiosa URL."""
    # Split on '?' to remove any query parameters
    base_url = url.split("?")[0]
    # Get the last part of the URL path
    deck_id = base_url.rstrip("/").split("/")[-1]
    return deck_id


def scrape_Curosa(deck_url, name):
    """Scrape deck data from Curiosa and save to file.

    Retries once after 30 seconds only if the API returns a 400 error.
    """
    deck_id = get_deck_id(deck_url)

    for attempt in range(2):  # Try up to 2 times (only retry on 400)
        try:
            response = requests.get(
                "https://curiosa.io/api/decks?ids=" + deck_id,
                timeout=30,
                verify=_REQUESTS_VERIFY,
            )

            if response.status_code == 400:
                # Only retry with 30 second delay on 400 errors
                print(f"API returned 400 error (attempt {attempt + 1})")
                if attempt == 0:
                    print("Retrying in 30 seconds...")
                    time.sleep(30)
                    continue
                return "{}"

            if response.status_code != 200:
                # Other non-200 errors - don't retry
                print(
                    f"Failed to retrieve the website. Status code: {response.status_code}"
                )
                return "{}"

            json_data = json.loads(response.text)

            # Check if we got a valid list with data
            if not isinstance(json_data, list) or len(json_data) == 0:
                print(f"API did not return a valid list. Got: {type(json_data)}")
                return "{}"

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
            return json.dumps(json_data[0])

        except requests.exceptions.Timeout:
            print(f"Request timed out (attempt {attempt + 1})")
            return "{}"
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return "{}"
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            print(f"Failed to parse response: {e}")
            return "{}"

    return "{}"


async def scrape_curosa_async(deck_url: str) -> str:
    """Fetch deck data from Curiosa asynchronously using aiohttp.

    Retries once after 30 seconds only if the API returns a 400 error.
    Returns a JSON string of the deck data, or '{}' on any failure.
    Unlike the sync version, does NOT write to a local file.
    """
    import aiohttp
    import ssl

    try:
        ssl_ctx = ssl.create_default_context()
        if _REQUESTS_VERIFY and _REQUESTS_VERIFY is not True:
            # certifi path returned
            import certifi as _certifi
            ssl_ctx = ssl.create_default_context(cafile=_certifi.where())
    except Exception:
        ssl_ctx = True  # aiohttp default SSL

    deck_id = get_deck_id(deck_url)
    url = "https://curiosa.io/api/decks?ids=" + deck_id

    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=ssl_ctx) as resp:
                    if resp.status == 400:
                        if attempt == 0:
                            await asyncio.sleep(30)
                            continue
                        return "{}"
                    if resp.status != 200:
                        return "{}"
                    json_data = await resp.json(content_type=None)
                    if not isinstance(json_data, list) or len(json_data) == 0:
                        return "{}"
                    return json.dumps(json_data[0])
        except asyncio.TimeoutError:
            return "{}"
        except Exception:
            return "{}"
    return "{}"


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
