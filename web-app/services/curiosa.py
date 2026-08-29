"""Curiosa/sorcerytcg.com API service for deck data."""

import json
import logging
import time
import urllib.parse
import requests

logger = logging.getLogger(__name__)

# Rate limit: minimum seconds between API requests
CURIOSA_REQUEST_DELAY = 20

# sorcerytcg.com tRPC API (formerly curiosa.io)
_TRPC_BASE = "https://sorcerytcg.com/api/trpc/deck.get"


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

        if engine.get("rules"):
            card["rules"] = engine["rules"]
        if engine.get("category"):
            card["category"] = engine["category"]

        if board == "Avatar":
            avatar.append(card)
        elif board == "Main":
            if engine.get("type") == "Site":
                atlas.append(card)
            else:
                spellbook.append(card)
        elif board == "Maybeboard":
            sideboard.append(card)
        # Skip "Collection" board

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


class CuriosaService:
    """Service for interacting with sorcerytcg.com API (formerly Curiosa)."""

    def __init__(self):
        self._last_request_time = 0

    def _rate_limit(self):
        """Wait if needed to respect the delay between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < CURIOSA_REQUEST_DELAY and self._last_request_time > 0:
            wait = CURIOSA_REQUEST_DELAY - elapsed
            logger.info(f"Rate limiting: waiting {wait:.1f}s before next API request")
            time.sleep(wait)
        self._last_request_time = time.time()

    def get_deck_id_from_url(self, url: str) -> str:
        """Extract deck ID from a Curiosa or sorcerytcg.com URL."""
        base_url = url.split("?")[0]
        deck_id = base_url.rstrip("/").split("/")[-1]
        return deck_id

    def _fetch_single_deck(self, deck_id: str) -> dict | None:
        """Fetch a single deck by ID from the tRPC API. Returns legacy dict or None."""
        input_json = json.dumps({"json": {"id": deck_id}})
        url = f"{_TRPC_BASE}?input={urllib.parse.quote(input_json)}"
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            logger.warning(f"API returned status {response.status_code} for deck {deck_id}")
            return None
        trpc_data = response.json()
        legacy = _convert_trpc_to_legacy(trpc_data)
        return legacy if legacy else None

    def fetch_deck_data(self, deck_url: str) -> str:
        """
        Fetch deck data from sorcerytcg.com API.
        Returns JSON string of deck data, or '{}' on failure.
        """
        try:
            deck_id = self.get_deck_id_from_url(deck_url)
            if not deck_id:
                logger.warning("Could not extract deck ID from URL")
                return "{}"

            self._rate_limit()
            legacy = self._fetch_single_deck(deck_id)
            if not legacy:
                return "{}"

            return json.dumps(legacy)

        except requests.exceptions.Timeout:
            logger.warning("API request timed out")
            return "{}"
        except requests.exceptions.RequestException as e:
            logger.warning(f"API request failed: {e}")
            return "{}"
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.warning(f"Failed to parse API response: {e}")
            return "{}"

    def fetch_decks_batch(self, urls: list[str]) -> tuple[list[dict], list[str]]:
        """Fetch multiple decks by URL, one tRPC call per deck.

        Args:
            urls: List of deck URLs (Curiosa or sorcerytcg.com).

        Returns:
            Tuple of (list of legacy deck dicts, list of error strings).
        """
        url_id_pairs = []
        errors = []
        for url in urls:
            if not url or not isinstance(url, str) or not url.strip():
                continue
            url = url.strip()
            deck_id = self.get_deck_id_from_url(url)
            if not deck_id:
                errors.append(f"Invalid URL: {url}")
                continue
            url_id_pairs.append((url, deck_id))

        if not url_id_pairs:
            return [], errors

        decks = []
        for deck_url, deck_id in url_id_pairs:
            self._rate_limit()
            try:
                legacy = self._fetch_single_deck(deck_id)
                if legacy:
                    decks.append(legacy)
                else:
                    errors.append(f"Deck not found: {deck_url}")
            except requests.exceptions.Timeout:
                logger.warning("API request timed out")
                errors.append(f"Request timed out: {deck_url}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"API request failed: {e}")
                errors.append(f"Request failed: {deck_url}")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse API response: {e}")
                errors.append(f"Parse error: {deck_url}")

        return decks, errors

    def fetch_deck_by_id(self, deck_id: str) -> dict | None:
        """Fetch a single deck by its ID. Returns legacy deck dict or None."""
        try:
            self._rate_limit()
            return self._fetch_single_deck(deck_id)
        except Exception as e:
            logger.warning(f"Failed to fetch deck {deck_id}: {e}")
        return None

    def fetch_decks_by_ids(self, deck_ids: list[str]) -> tuple[list[dict], list[str]]:
        """Fetch multiple decks by ID, one tRPC call per deck.

        Args:
            deck_ids: List of deck IDs.

        Returns:
            Tuple of (list of legacy deck dicts, list of failed deck IDs).
        """
        decks = []
        failed = []

        for deck_id in deck_ids:
            self._rate_limit()
            try:
                legacy = self._fetch_single_deck(deck_id)
                if legacy:
                    decks.append(legacy)
                else:
                    failed.append(deck_id)
            except Exception as e:
                logger.warning(f"Failed to fetch deck {deck_id}: {e}")
                failed.append(deck_id)

        return decks, failed
