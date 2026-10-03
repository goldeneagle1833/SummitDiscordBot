import asyncio
import json
import os
import re
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

# Play Sorcery Online hosts its own decks. A share link looks like
# https://playsorceryonline.com/?deck=pD-1gXa3cg8c and its public exporter
# hands the deck back in the same avatar/spellbook/atlas/sideboard shape
# sorcerytcg.com decks are stored in.
_PSO_HOST = "playsorceryonline.com"
_PSO_DECK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")
PSO_DECK_EXPORT_URL = "https://playsorceryonline.com/api/decks/export"
# Tags a stored deck as PSO-hosted so its id is never mistaken for a Curiosa id.
PSO_DECK_SOURCE = "sorcery_online"


def get_pso_deck_id(url: str) -> str | None:
    """Return the deck id from a Play Sorcery Online deck link, else None."""
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.netloc or "").lower().split(":")[0]
    if parsed.scheme not in ("http", "https"):
        return None
    if host != _PSO_HOST and not host.endswith("." + _PSO_HOST):
        return None
    deck_id = urllib.parse.parse_qs(parsed.query).get("deck", [""])[0].strip()
    return deck_id if _PSO_DECK_ID_RE.match(deck_id) else None


def pso_deck_url(deck_id: str) -> str:
    """The canonical share link for a PSO-hosted deck."""
    return f"https://{_PSO_HOST}/?deck={deck_id}"


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
    # A Sorcery Online deck link keeps only its deck id
    pso_id = get_pso_deck_id(url)
    if pso_id:
        return pso_deck_url(pso_id)
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
    maybeboard = []

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
        elif board in ("Collection", "Sideboard"):
            sideboard.append(card)
        elif board == "Maybeboard":
            # Cards the owner is only considering. Kept apart so they never
            # show up as part of the Collection.
            maybeboard.append(card)

    owner = deck.get("owner", {})
    return {
        "id": deck.get("id", ""),
        "name": deck.get("name", ""),
        "username": owner.get("username", ""),
        "avatar": avatar,
        "spellbook": spellbook,
        "atlas": atlas,
        "sideboard": sideboard,
        "maybeboard": maybeboard,
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


def _convert_pso_export_to_legacy(export: dict) -> dict:
    """Trim a Play Sorcery Online deck export to the legacy Curiosa format.

    PSO already answers in avatar/spellbook/atlas/sideboard sections, but its
    cards carry extra fields and no image. The deck is tagged with its source
    because PSO deck ids look nothing like Curiosa ids and must not be used as
    one (the website's "Try this Deck" launcher imports from Curiosa by id).
    """
    if not isinstance(export, dict):
        return {}

    sections = {}
    for section in ("avatar", "spellbook", "atlas", "sideboard"):
        cards = []
        for entry in export.get(section) or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            cards.append({
                "name": entry.get("name", ""),
                "quantity": entry.get("quantity", 1),
                "type": entry.get("type") or "Unknown",
                "rarity": entry.get("rarity") or "Unknown",
                "cost": entry.get("cost"),
                "elements": entry.get("elements") or "None",
                "image": "",
            })
        sections[section] = cards

    if not any(sections.values()):
        return {}

    return {
        "id": export.get("id", ""),
        "name": export.get("name", ""),
        "username": export.get("username", ""),
        "source": PSO_DECK_SOURCE,
        **sections,
    }


def fetch_sorcery_online_deck(deck_url: str) -> dict | None:
    """Fetch a PSO-hosted deck through PSO's public exporter.

    Returns the legacy-format dict or None on failure. The link itself is not
    logged: PSO share links are effectively the deck's password.
    """
    pso_id = get_pso_deck_id(deck_url)
    if not pso_id:
        return None
    try:
        response = requests.get(
            PSO_DECK_EXPORT_URL,
            params={"input": pso_deck_url(pso_id)},
            timeout=30,
            verify=_REQUESTS_VERIFY,
        )
        if response.status_code != 200:
            return None
        legacy = _convert_pso_export_to_legacy(response.json())
    except Exception:
        return None
    return legacy if legacy else None


def fetch_deck_by_url(deck_url: str) -> dict | None:
    """Fetch a deck from whichever service the link points at.

    Returns the legacy-format dict or None on failure.
    """
    if get_pso_deck_id(deck_url):
        return fetch_sorcery_online_deck(deck_url)
    deck_id = get_deck_id(deck_url)
    if not deck_id:
        return None
    return _fetch_deck_from_api(deck_id)


def _append_deck_to_file(legacy_deck: dict, name: str) -> None:
    """Append a scraped deck to the on-disk deck log (best effort)."""
    if os.path.exists(name):
        with open(name, "r") as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = []
    else:
        existing_data = []

    existing_data.append(legacy_deck)

    with open(name, "w") as f:
        json.dump(existing_data, f, indent=2)


def scrape_Curosa(deck_url, name):
    """Fetch deck data from sorcerytcg.com or Sorcery Online and save to file.

    Retries once after 30 seconds only if the sorcerytcg.com API returns a
    400 error.
    """
    if get_pso_deck_id(deck_url):
        legacy_deck = fetch_sorcery_online_deck(deck_url)
        if not legacy_deck:
            print("Sorcery Online did not return valid deck data.")
            return "{}"
        _append_deck_to_file(legacy_deck, name)
        return json.dumps(legacy_deck)

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

            _append_deck_to_file(legacy_deck, name)

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
        try:
            legacy = fetch_deck_by_url(deck_url)
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
