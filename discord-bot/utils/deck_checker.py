import asyncio
import json
import os
import time
import urllib.parse
import requests
try:
    import certifi
    _REQUESTS_VERIFY = certifi.where()
    _SSL_CONTEXT = None  # aiohttp uses ssl.create_default_context() with certifi if available
except Exception:
    _REQUESTS_VERIFY = True
    _SSL_CONTEXT = None

# sorcerytcg.com tRPC API (formerly curiosa.io)
_TRPC_BASE = "https://sorcerytcg.com/api/trpc/deck.get"


def get_deck_id(url: str) -> str:
    """Extract deck ID from a Curiosa or sorcerytcg.com URL.

    Handles URLs like:
        https://sorcerytcg.com/decks/abc123
        https://sorcerytcg.com/decks/abc123/edit?filters=e:fire,t:magic
    """
    # Strip query parameters
    base_url = url.split("?")[0]
    parts = base_url.rstrip("/").split("/")
    # Skip trailing path segments that aren't the deck ID (e.g. /edit)
    _NON_ID_SEGMENTS = {"edit", "view", "copy"}
    while parts and parts[-1].lower() in _NON_ID_SEGMENTS:
        parts.pop()
    return parts[-1] if parts else ""


def clean_deck_url(url: str) -> str:
    """Normalize a sorcerytcg.com / curiosa.io deck URL by stripping query
    params and trailing /edit suffix.

    DraftSorcery and other URLs are returned unchanged since their query
    params carry meaningful data (e.g. ``?deck=...``).
    """
    if not url or not isinstance(url, str):
        return url
    # Only clean sorcerytcg.com and curiosa.io URLs
    lower = url.lower()
    if "sorcerytcg.com" not in lower and "curiosa.io" not in lower:
        return url
    # Strip query parameters
    base = url.split("?")[0].rstrip("/")
    # Remove trailing /edit, /view, /copy segments
    _NON_ID_SEGMENTS = {"edit", "view", "copy"}
    parts = base.split("/")
    while len(parts) > 1 and parts[-1].lower() in _NON_ID_SEGMENTS:
        parts.pop()
    return "/".join(parts)


def _convert_trpc_to_legacy(trpc_response: dict) -> dict:
    """Convert a sorcerytcg.com tRPC deck response to the legacy Curiosa format.

    The legacy format uses avatar/spellbook/atlas/sideboard sections with flat
    card dicts.  All downstream consumers expect this shape, so we convert at
    the API boundary.
    """
    deck = trpc_response.get("result", {}).get("data", {}).get("json", {})
    if not deck:
        return {}

    avatar = []
    spellbook = []
    atlas = []
    sideboard = []

    for entry in deck.get("decklist", []):
        board = entry.get("board", "")
        card_info = entry.get("card", {})
        engine = card_info.get("engine", {})
        printing = entry.get("printing", {})
        printing_meta = printing.get("meta", {})

        # Build a flat card dict matching the old Curiosa format
        elements_list = engine.get("elements", [])
        elements_str = ", ".join(elements_list) if elements_list else "None"

        card = {
            "name": card_info.get("name", ""),
            "quantity": entry.get("quantity", 1),
            "type": engine.get("type", "Unknown"),
            "rarity": engine.get("rarity", "Unknown"),
            "cost": engine.get("cost"),
            "elements": elements_str,
            "image": printing_meta.get("image", ""),
        }

        # Optional fields from old format
        if engine.get("rules"):
            card["rules"] = engine["rules"]
        if engine.get("category"):
            card["category"] = engine["category"]

        # Route to the correct section based on board + type
        if board == "Avatar":
            avatar.append(card)
        elif board == "Main":
            if engine.get("type") == "Site":
                atlas.append(card)
            else:
                spellbook.append(card)
        elif board in ("Maybeboard", "Collection", "Sideboard"):
            sideboard.append(card)

    owner = deck.get("owner", {})
    return {
        "id": deck.get("id", ""),
        "name": deck.get("name", ""),
        "username": owner.get("username", ""),
        "avatar": avatar,
        "spellbook": spellbook,
        "atlas": atlas,
        "sideboard": sideboard,
    }


def _fetch_deck_from_api(deck_id: str) -> dict | None:
    """Fetch a single deck from the sorcerytcg.com tRPC API.

    Returns the legacy-format dict or None on failure.
    """
    input_json = json.dumps({"json": {"id": deck_id}})
    url = f"{_TRPC_BASE}?input={urllib.parse.quote(input_json)}"
    response = requests.get(url, timeout=30, verify=_REQUESTS_VERIFY)
    if response.status_code != 200:
        return None
    trpc_data = response.json()
    legacy = _convert_trpc_to_legacy(trpc_data)
    return legacy if legacy else None


def scrape_Curosa(deck_url, name):
    """Fetch deck data from sorcerytcg.com and save to file.

    Retries once after 30 seconds only if the API returns a 400 error.
    """
    deck_id = get_deck_id(deck_url)
    input_json = json.dumps({"json": {"id": deck_id}})
    api_url = f"{_TRPC_BASE}?input={urllib.parse.quote(input_json)}"

    for attempt in range(2):  # Try up to 2 times (only retry on 400)
        try:
            response = requests.get(
                api_url,
                timeout=30,
                verify=_REQUESTS_VERIFY,
            )

            if response.status_code == 400:
                print(f"API returned 400 error (attempt {attempt + 1})")
                if attempt == 0:
                    print("Retrying in 30 seconds...")
                    time.sleep(30)
                    continue
                return "{}"

            if response.status_code != 200:
                print(
                    f"Failed to retrieve the website. Status code: {response.status_code}"
                )
                return "{}"

            trpc_data = json.loads(response.text)
            legacy_deck = _convert_trpc_to_legacy(trpc_data)

            if not legacy_deck:
                print("API did not return valid deck data.")
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
            existing_data.append(legacy_deck)

            # Write the updated data back to the file
            with open(name, "w") as f:
                json.dump(existing_data, f, indent=2)

            # Return json data as a string to save in the db
            return json.dumps(legacy_deck)

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
    """Fetch deck data from sorcerytcg.com asynchronously.

    Runs the synchronous requests.get call in a thread to avoid blocking
    the event loop.
    Returns a JSON string of the deck data, or '{}' on any failure.
    """
    def _fetch() -> str:
        deck_id = get_deck_id(deck_url)
        if not deck_id:
            return "{}"
        try:
            legacy = _fetch_deck_from_api(deck_id)
            if not legacy:
                return "{}"
            return json.dumps(legacy)
        except Exception:
            return "{}"

    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
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
