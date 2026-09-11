"""Curiosa/sorcerytcg.com API service for deck data."""

import json
import logging
import re
import time
import urllib.parse
import requests

logger = logging.getLogger(__name__)

# Rate limit: minimum seconds between API requests
CURIOSA_REQUEST_DELAY = 20

# sorcerytcg.com tRPC API (formerly curiosa.io)
_TRPC_BASE = "https://sorcerytcg.com/api/trpc/deck.get"
_TRPC_BASE_ROOT = "https://sorcerytcg.com/api/trpc"

_EVENT_URL_RE = re.compile(
    r"https?://(?:play\.)?sorcerytcg\.com/events/([A-Za-z0-9_-]+)", re.IGNORECASE
)


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

    # ── Event snapshot import ─────────────────────────────────────────────

    @staticmethod
    def get_event_id_from_url(url: str) -> str | None:
        """Extract event ID from a sorcerytcg.com event URL."""
        match = _EVENT_URL_RE.match(url.strip())
        return match.group(1) if match else None

    def fetch_event_deck_ids(
        self, event_url: str, on_progress=None
    ) -> dict:
        """Discover all player deck IDs from a sorcerytcg.com event URL.

        Fetches the event player list, scrapes the page for standings order,
        then batch-fetches playerSnapshot for each player to extract their
        registered sourceDeck ID.  Players are returned sorted by standing.

        Returns:
            {
                "event_name": str,
                "event_date": str | None,
                "top_cut_size": int,
                "players": [{"name": str, "deck_id": str, "standing": int}, ...],
                "errors": [str, ...],
            }
        """
        event_id = self.get_event_id_from_url(event_url)
        if not event_id:
            raise ValueError(
                "URL must be in the format https://sorcerytcg.com/events/{id}"
            )

        if on_progress:
            on_progress("Fetching event data...")

        # Step 1: Fetch event to get player list
        event = self._fetch_event_trpc(event_id)
        event_name = event.get("title", "")
        event_date = (event.get("startsAt") or "")[:10] or None
        try:
            top_cut_size = int(event.get("topcut") or 8)
        except (TypeError, ValueError):
            top_cut_size = 8
        players_data = event.get("players", [])

        # Filter to players that are not dropped (or have seats = played games)
        active_players = [
            p for p in players_data
            if p.get("status") != "Dropped" or p.get("seats")
        ]

        if not active_players:
            return {
                "event_name": event_name,
                "event_date": event_date,
                "top_cut_size": top_cut_size,
                "players": [],
                "errors": ["No active players found in this event"],
            }

        # Step 2: Scrape the event page HTML for authoritative standings order
        if on_progress:
            on_progress("Fetching standings from event page...")
        html_standings = self._fetch_page_standings(event_url)

        # Compute Swiss scores as fallback for sorting
        player_swiss = {}
        for player in active_players:
            user = player.get("user", {})
            name = user.get("displayname") or user.get("username") or "Unknown"
            seats = player.get("seats", [])
            swiss_score = sum(
                s.get("result", {}).get("score", 0) for s in seats
                if s.get("round", {}).get("phase", {}).get("structure") == "Swiss"
            )
            player_swiss[player["id"]] = {"name": name, "swiss_score": swiss_score}

        # Sort active players by standings (HTML source of truth, Swiss fallback)
        fallback_rank = len(html_standings) + 1 if html_standings else 1
        active_players.sort(
            key=lambda p: (
                html_standings.get(
                    player_swiss[p["id"]]["name"], fallback_rank
                ),
                -player_swiss[p["id"]]["swiss_score"],
            )
        )

        if on_progress:
            on_progress(f"Found {len(active_players)} players, fetching deck snapshots...")

        # Step 3: Batch-fetch playerSnapshot for all players
        player_deck_ids = []
        errors = []
        BATCH_SIZE = 10

        for i in range(0, len(active_players), BATCH_SIZE):
            batch = active_players[i:i + BATCH_SIZE]
            if on_progress:
                on_progress(
                    f"Fetching snapshots {i + 1}-{min(i + len(batch), len(active_players))}"
                    f" of {len(active_players)}..."
                )

            batch_results = self._fetch_player_snapshots_batch(event_id, batch)
            for player, result in zip(batch, batch_results):
                user = player.get("user", {})
                name = user.get("displayname") or user.get("username") or "Unknown"
                standing = html_standings.get(name, fallback_rank)
                if result is None:
                    errors.append(f"No deck snapshot for {name}")
                    continue
                source_deck = result.get("sourceDeck")
                if not source_deck or not source_deck.get("id"):
                    errors.append(f"No source deck found for {name}")
                    continue
                player_deck_ids.append({
                    "name": name,
                    "deck_id": source_deck["id"],
                    "standing": standing,
                })

        return {
            "event_name": event_name,
            "event_date": event_date,
            "top_cut_size": top_cut_size,
            "players": player_deck_ids,
            "errors": errors,
        }

    @staticmethod
    def _fetch_page_standings(event_url: str) -> dict[str, int]:
        """Scrape the event page HTML for Play Network standings order.

        Returns a dict mapping display_name -> position (1-indexed).
        Returns empty dict if parsing fails.
        """
        try:
            resp = requests.get(
                event_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code != 200:
                logger.warning("Failed to fetch page standings: HTTP %s", resp.status_code)
                return {}
            entries = re.findall(
                r'<span class="w-4 text-center font-title text-lg">(\d+)</span>.*?'
                r'<span class="truncate font-title">(.*?)</span>',
                resp.text,
                re.DOTALL,
            )
            standings = {}
            for pos_str, name in entries:
                name = name.strip()
                if name and name not in standings:
                    standings[name] = int(pos_str)
            if standings:
                logger.info("Parsed %d standings from event page", len(standings))
            else:
                logger.warning("Parsed 0 standings from page HTML")
            return standings
        except Exception as exc:
            logger.warning("Could not parse page standings: %s", exc)
            return {}

    def _fetch_event_trpc(self, event_id: str) -> dict:
        """Fetch event data from sorcerytcg.com tRPC endpoint."""
        params = {
            "batch": "1",
            "input": json.dumps({"0": {"json": {"id": event_id}}}),
        }
        resp = requests.get(
            f"{_TRPC_BASE_ROOT}/event.get", params=params, timeout=15
        )
        if resp.status_code != 200:
            raise ValueError(
                f"sorcerytcg.com returned {resp.status_code} for event {event_id}"
            )
        try:
            return resp.json()[0]["result"]["data"]["json"]["event"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Unexpected event response format: {exc}") from exc

    def _fetch_player_snapshots_batch(
        self, event_id: str, players: list[dict]
    ) -> list[dict | None]:
        """Batch-fetch event.playerSnapshot for a list of players.

        Returns a list of snapshot dicts (or None for failures), one per player.
        """
        if not players:
            return []

        # Build batched tRPC request
        input_data = {}
        for j, player in enumerate(players):
            input_data[str(j)] = {
                "json": {
                    "eventId": event_id,
                    "playerId": player["id"],
                }
            }

        path = ",".join(["event.playerSnapshot"] * len(players))
        try:
            resp = requests.get(
                f"{_TRPC_BASE_ROOT}/{path}",
                params={"batch": "1", "input": json.dumps(input_data)},
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("Batch snapshot fetch failed: %s", exc)
            return [None] * len(players)

        if resp.status_code != 200:
            logger.warning("Batch snapshot fetch returned %s", resp.status_code)
            return [None] * len(players)

        results = []
        try:
            body = resp.json()
            for j in range(len(players)):
                if j < len(body):
                    snapshot = (
                        body[j]
                        .get("result", {})
                        .get("data", {})
                        .get("json", {})
                    )
                    results.append(snapshot if snapshot else None)
                else:
                    results.append(None)
        except (TypeError, AttributeError) as exc:
            logger.warning("Error parsing batch snapshot response: %s", exc)
            return [None] * len(players)

        return results
