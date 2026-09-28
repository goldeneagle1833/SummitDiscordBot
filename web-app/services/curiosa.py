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

# ── Deck links ────────────────────────────────────────────────────────────
#
# Players share decks from two places:
#   - sorcerytcg.com (formerly curiosa.io): https://sorcerytcg.com/decks/<id>
#   - Play Sorcery Online (PSO), which hosts its own decks:
#     https://playsorceryonline.com/?deck=<id>
# PSO puts the deck id in the query string, so the old "strip everything after
# the ?" normalisation would collapse every PSO deck into one. These helpers
# are the single place that knows both shapes.

_CURIOSA_HOSTS = ("curiosa.io", "sorcerytcg.com")
_PSO_HOST = "playsorceryonline.com"
_PSO_DECK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")
_CURIOSA_DECK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
# Path segments the deckbuilder appends after the id; not part of the id.
_NON_ID_SEGMENTS = {"edit", "view", "copy"}
# PSO's public exporter: hand it a deck link, get the deck back.
PSO_DECK_EXPORT_URL = "https://playsorceryonline.com/api/decks/export"
# Marks a legacy-format deck as PSO-hosted, so its id is not mistaken for a
# Curiosa id (which the "Try this Deck" launcher needs).
PSO_DECK_SOURCE = "sorcery_online"


def _split_url(url):
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    return parsed


def _host_matches(netloc: str, host: str) -> bool:
    netloc = (netloc or "").lower().split(":")[0]
    return netloc == host or netloc.endswith("." + host)


def get_pso_deck_id(url: str) -> str | None:
    """Return the deck id from a Play Sorcery Online deck link, else None."""
    parsed = _split_url(url)
    if not parsed or not _host_matches(parsed.netloc, _PSO_HOST):
        return None
    deck_id = urllib.parse.parse_qs(parsed.query).get("deck", [""])[0].strip()
    return deck_id if _PSO_DECK_ID_RE.match(deck_id) else None


def get_curiosa_deck_id(url: str) -> str | None:
    """Return the deck id from a sorcerytcg.com / curiosa.io deck link, else None."""
    parsed = _split_url(url)
    if not parsed or not any(_host_matches(parsed.netloc, h) for h in _CURIOSA_HOSTS):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    while parts and parts[-1].lower() in _NON_ID_SEGMENTS:
        parts.pop()
    if len(parts) != 2 or parts[0].lower() != "decks":
        return None
    return parts[1] if _CURIOSA_DECK_ID_RE.match(parts[1]) else None


def pso_deck_url(deck_id: str) -> str:
    """The canonical share link for a PSO-hosted deck."""
    return f"https://{_PSO_HOST}/?deck={deck_id}"


def is_deck_url(url: str) -> bool:
    """True for a deck link from either sorcerytcg.com or Play Sorcery Online."""
    return bool(get_pso_deck_id(url) or get_curiosa_deck_id(url))


def deck_url_source(url: str) -> str | None:
    """'sorcery_online', 'curiosa', or None for anything else."""
    if get_pso_deck_id(url):
        return PSO_DECK_SOURCE
    if get_curiosa_deck_id(url):
        return "curiosa"
    return None


def normalize_deck_url(url: str) -> str:
    """Canonical form of a deck link, so one deck groups as one on a profile.

    Curiosa links lose their query string and any trailing /edit; PSO links keep
    only the deck id. Anything else just loses its query string, as before.
    """
    if not url or not isinstance(url, str):
        return url
    pso_id = get_pso_deck_id(url)
    if pso_id:
        return pso_deck_url(pso_id)
    curiosa_id = get_curiosa_deck_id(url)
    if curiosa_id:
        parsed = _split_url(url)
        return f"{parsed.scheme}://{parsed.netloc}/decks/{curiosa_id}"
    return url.split("?")[0]


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


def _convert_pso_export_to_legacy(export: dict) -> dict:
    """Convert a Play Sorcery Online deck export to the legacy Curiosa format.

    PSO's exporter already answers in avatar/spellbook/atlas/sideboard sections,
    but its cards carry extra fields and no image, so trim each card to the
    shape every consumer expects. The deck is tagged with its source because
    PSO deck ids look nothing like Curiosa ids and must not be used as one.
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


class CuriosaService:
    """Service for fetching decks from sorcerytcg.com (formerly Curiosa) and
    Play Sorcery Online, returned in the shared legacy format."""

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

    def _fetch_pso_deck(self, deck_id: str) -> dict | None:
        """Fetch a PSO-hosted deck through PSO's public exporter.

        PSO is a separate service from sorcerytcg.com, so the Curiosa rate
        limit does not apply here.
        """
        response = requests.get(
            PSO_DECK_EXPORT_URL, params={"input": pso_deck_url(deck_id)}, timeout=30
        )
        if response.status_code != 200:
            logger.warning(
                f"Sorcery Online returned status {response.status_code} for deck {deck_id}"
            )
            return None
        legacy = _convert_pso_export_to_legacy(response.json())
        return legacy if legacy else None

    def _fetch_by_url(self, deck_url: str) -> dict | None:
        """Fetch a deck from whichever service the link points at."""
        pso_id = get_pso_deck_id(deck_url)
        if pso_id:
            return self._fetch_pso_deck(pso_id)
        deck_id = self.get_deck_id_from_url(deck_url)
        if not deck_id:
            logger.warning("Could not extract deck ID from URL")
            return None
        self._rate_limit()
        return self._fetch_single_deck(deck_id)

    def fetch_deck_data(self, deck_url: str) -> str:
        """
        Fetch deck data for a sorcerytcg.com or Play Sorcery Online deck link.
        Returns JSON string of deck data, or '{}' on failure.
        """
        try:
            legacy = self._fetch_by_url(deck_url)
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
        deck_urls = []
        errors = []
        for url in urls:
            if not url or not isinstance(url, str) or not url.strip():
                continue
            url = url.strip()
            if not get_pso_deck_id(url) and not self.get_deck_id_from_url(url):
                errors.append(f"Invalid URL: {url}")
                continue
            deck_urls.append(url)

        if not deck_urls:
            return [], errors

        decks = []
        for deck_url in deck_urls:
            try:
                legacy = self._fetch_by_url(deck_url)
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
                "event_id": str,
                "top_cut_size": int,
                "players": [{"name": str, "deck_id": str, "standing": int}, ...],
                "match_history": [<see _build_match_history>, ...],
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
                "event_id": event_id,
                "top_cut_size": top_cut_size,
                "players": [],
                "match_history": [],
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
        deck_by_registration = {}
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
                deck_by_registration[player["id"]] = source_deck["id"]
                player_deck_ids.append({
                    "name": name,
                    "deck_id": source_deck["id"],
                    "standing": standing,
                })

        match_history = self._build_match_history(
            active_players, deck_by_registration, html_standings, fallback_rank
        )

        return {
            "event_name": event_name,
            "event_date": event_date,
            "event_id": event_id,
            "top_cut_size": top_cut_size,
            "players": player_deck_ids,
            "match_history": match_history,
            "errors": errors,
        }

    @staticmethod
    def _build_match_history(
        players: list[dict],
        deck_by_registration: dict[str, str],
        html_standings: dict[str, int],
        fallback_rank: int,
    ) -> list[dict]:
        """Build a round-by-round match list for every player in the event.

        Each entry describes one player and their matches in descending round
        order (most recent first), with the opponent resolved from the pairing.
        """
        by_registration = {p["id"]: p for p in players if p.get("id")}

        def describe(registration_id, embedded_user=None):
            user = by_registration.get(registration_id, {}).get("user") or embedded_user or {}
            return {
                "registration_id": registration_id or "",
                "display_name": (
                    user.get("displayname") or user.get("username") or "Unknown"
                ),
                "username": user.get("username", ""),
                "deck_id": deck_by_registration.get(registration_id, ""),
                "profile_image": (
                    (user.get("feature") or {}).get("meta") or {}
                ).get("image", ""),
            }

        history = []
        for player in players:
            registration_id = player.get("id")
            if not registration_id:
                continue

            matches = []
            wins = losses = draws = 0
            for seat in player.get("seats", []):
                round_info = seat.get("round") or {}
                result_info = seat.get("result") or {}
                outcome = result_info.get("result")

                opponent = None
                for other in (seat.get("pairing") or {}).get("seats", []):
                    if other.get("registrationId") == registration_id:
                        continue
                    # Dropped players are absent from the player list, so fall
                    # back to the copy of the user embedded in the pairing.
                    opponent = describe(
                        other.get("registrationId"),
                        (other.get("registration") or {}).get("user"),
                    )
                    break

                if outcome == "Win":
                    wins += 1
                elif outcome == "Loss":
                    losses += 1
                elif outcome == "Draw":
                    draws += 1

                matches.append({
                    "round": round_info.get("number"),
                    "phase": (round_info.get("phase") or {}).get("structure", ""),
                    "result": outcome,
                    "is_bye": bool(result_info.get("isBye")),
                    "opponent": opponent,
                })

            if not matches:
                continue

            matches.sort(key=lambda m: m["round"] or 0, reverse=True)
            entry = describe(registration_id)
            entry.update({
                "standing": html_standings.get(entry["display_name"], fallback_rank),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "matches": matches,
            })
            history.append(entry)

        history.sort(key=lambda e: e["standing"])
        return history

    def fetch_event_match_history(self, event_url: str, on_progress=None) -> dict:
        """Fetch the round-by-round pairings for a sorcerytcg.com event.

        Returns a payload suitable for EventRepository.save_match_history().
        """
        discovery = self.fetch_event_deck_ids(event_url, on_progress=on_progress)
        return {
            "event_id": discovery.get("event_id", ""),
            "event_url": event_url,
            "event_title": discovery.get("event_name", ""),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "players": discovery.get("match_history", []),
            "errors": discovery.get("errors", []),
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
            from services.explorer import ExplorerService
            standings = ExplorerService._parse_page_standings(resp.text)
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
