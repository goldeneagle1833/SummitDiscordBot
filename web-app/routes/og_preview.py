"""Open Graph preview routes for Discord/social media link embeds.

Discord and other social platforms don't execute JavaScript, so they can't
read meta tags set by the React SPA. Nginx routes /top-8 and /deck-rec
paths to Flask. Flask checks the user agent: bot crawlers get minimal HTML
with dynamic OG meta tags, regular users get the React SPA index.html.
"""

import logging
import re
import os

from flask import Blueprint, request, send_from_directory

from repositories.events import EventRepository
from repositories.deck_rec_repo import DeckRecRepository
from repositories.elo import EloRepository
from repositories.card_catalog import CardCatalogRepository
from services.player import PlayerService
from utils.formatting import format_event_name
from webapp_config import AVATAR_IMAGES_DIR, MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)

og_preview_bp = Blueprint("og_preview", __name__)

SITE_URL = "https://sorcererssummit.com"
SITE_NAME = "Sorcerers Summit"
DEFAULT_IMAGE = f"{SITE_URL}/static/images/favicon.png"
THEME_COLOR = "#1a1a2e"

# Path to the React SPA build output
_SPA_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

BOT_USER_AGENTS = re.compile(
    r"Discordbot|facebookexternalhit|Twitterbot|LinkedInBot|Slackbot|WhatsApp|TelegramBot",
    re.IGNORECASE,
)


def _is_bot() -> bool:
    """Check if the request is from a known bot crawler."""
    ua = request.headers.get("User-Agent", "")
    return bool(BOT_USER_AGENTS.search(ua))


def _serve_spa():
    """Serve the React SPA index.html for regular (non-bot) users."""
    return send_from_directory(os.path.abspath(_SPA_DIR), "index.html")


def _resolve_avatar_image_url(avatar_name: str) -> str | None:
    """Find the avatar image file and return its public URL."""
    if not avatar_name or not AVATAR_IMAGES_DIR.exists():
        return None
    norm = re.sub(r'[^a-z0-9]', '', avatar_name.lower())
    for fname in os.listdir(AVATAR_IMAGES_DIR):
        if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        fname_norm = re.sub(r'[^a-z0-9]', '', fname.rsplit('.', 1)[0].lower())
        if norm in fname_norm or fname_norm.startswith(norm):
            return f"{SITE_URL}/avatar-images/{fname}"
    return None


def _og_html(title: str, description: str, url: str, image: str | None = None) -> str:
    """Render minimal HTML with Open Graph meta tags."""
    image = image or DEFAULT_IMAGE
    # Escape HTML entities in dynamic content
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta property="og:title" content="{esc(title)}" />
  <meta property="og:description" content="{esc(description)}" />
  <meta property="og:image" content="{esc(image)}" />
  <meta property="og:url" content="{esc(url)}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="{esc(SITE_NAME)}" />
  <meta name="theme-color" content="{THEME_COLOR}" />
  <meta http-equiv="refresh" content="0;url={esc(url)}" />
  <title>{esc(title)}</title>
</head>
<body></body>
</html>"""


@og_preview_bp.route("/top-8")
def og_events_list():
    """OG preview for the events listing page."""
    if not _is_bot():
        return _serve_spa()

    try:
        repo = EventRepository()
        events = repo.get_all_events()
        count = len(events) if events else 0
        description = f"Browse {count} tournament events with top 8 decklists for Sorcery: Contested Realm"
    except Exception:
        description = "Tournament top 8 decklists for Sorcery: Contested Realm"

    return _og_html(
        title="Top 8 Events — Sorcerers Summit",
        description=description,
        url=f"{SITE_URL}/top-8",
    )


@og_preview_bp.route("/top-8/<event_folder>")
def og_event_detail(event_folder: str):
    """OG preview for a specific event page."""
    if not _is_bot():
        return _serve_spa()

    try:
        repo = EventRepository()
        decks = repo.get_event_decks(event_folder)
        description_text = repo.get_event_description(event_folder)
        event_name = format_event_name(event_folder)

        if decks and decks.get("top8_decks"):
            top8 = decks["top8_decks"]
            deck_count = len(top8) + len(decks.get("all_decks") or [])
            winner = top8[0].get("player", "") if top8 else ""
            winner_avatar = top8[0].get("avatar", "") if top8 else ""

            if description_text:
                description = description_text
            elif winner:
                description = f"{deck_count} decklists | Won by {winner}"
            else:
                description = f"{deck_count} decklists from {event_name}"

            image = _resolve_avatar_image_url(winner_avatar)
        else:
            description = description_text or f"Decklists from {event_name}"
            image = None
    except Exception:
        event_name = format_event_name(event_folder)
        description = f"Decklists from {event_name}"
        image = None

    return _og_html(
        title=f"{event_name} — Sorcerers Summit",
        description=description,
        url=f"{SITE_URL}/top-8/{event_folder}",
        image=image,
    )


@og_preview_bp.route("/deck-rec")
def og_deck_rec_list():
    """OG preview for the deck recommendations listing page."""
    if not _is_bot():
        return _serve_spa()

    return _og_html(
        title="Deck Recommendations — Sorcerers Summit",
        description="Browse tournament-proven archetypes and community deck recommendations for Sorcery: Contested Realm",
        url=f"{SITE_URL}/deck-rec",
    )


@og_preview_bp.route("/deck-rec/<deck_id>")
def og_deck_detail(deck_id: str):
    """OG preview for a specific deck recommendation page."""
    if not _is_bot():
        return _serve_spa()

    try:
        repo = DeckRecRepository()
        all_decks = repo.load_all_decks()
        seed = next((d for d in all_decks if d.deck_id == deck_id and d.is_seed), None)

        if seed:
            title = seed.deck_name or "Deck Recommendation"
            parts = []
            if seed.avatar_name:
                parts.append(seed.avatar_name)
            if seed.player_name:
                parts.append(f"by {seed.player_name}")
            if seed.event_name:
                parts.append(f"from {seed.event_name}")

            if seed.primer:
                description = seed.primer
            elif parts:
                description = " | ".join(parts)
            else:
                description = "Sorcery: Contested Realm deck recommendation"

            image = _resolve_avatar_image_url(seed.avatar_name)
        else:
            title = "Deck Recommendation"
            description = "Sorcery: Contested Realm deck recommendation"
            image = None
    except Exception:
        title = "Deck Recommendation"
        description = "Sorcery: Contested Realm deck recommendation"
        image = None

    return _og_html(
        title=f"{title} — Sorcerers Summit",
        description=description,
        url=f"{SITE_URL}/deck-rec/{deck_id}",
        image=image,
    )


def _get_avatar_stats(avatar_name: str) -> dict | None:
    """Query all-time win/loss stats for an avatar across all match sources.

    Mirrors the ?event=all&source=all logic used by the avatar API:
    - match_records (current event, Discord matches)
    - match_records_archive (past events)
    - match_records non-Discord sources
    - external_matches table
    """
    import sqlite3, json as _json

    if not MATCH_RECORDS_DB_PATH.exists():
        return None

    norm = avatar_name.lower().strip()
    wins = losses = 0

    _DECK_NOT_EMPTY = (
        "((json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}')"
        " OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}'))"
    )

    def _tally(rows):
        nonlocal wins, losses
        for row in rows:
            for col, is_win in ((row[0], True), (row[1], False)):
                if not col or col in ("", "{}"):
                    continue
                try:
                    d = _json.loads(col)
                    avatar_list = d.get("avatar", [])
                    if avatar_list and avatar_list[0].get("name", "").lower().strip() == norm:
                        if is_win:
                            wins += 1
                        else:
                            losses += 1
                except Exception:
                    pass

    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        # Current event Discord matches
        try:
            cur.execute(
                f"SELECT json_deck_data_winner, json_deck_data_loser FROM match_records "
                f"WHERE {_DECK_NOT_EMPTY} AND (source = 'Discord' OR source IS NULL)"
            )
            _tally(cur.fetchall())
        except sqlite3.OperationalError:
            pass

        # Archived past-event matches
        try:
            cur.execute(
                f"SELECT json_deck_data_winner, json_deck_data_loser FROM match_records_archive "
                f"WHERE {_DECK_NOT_EMPTY}"
            )
            _tally(cur.fetchall())
        except sqlite3.OperationalError:
            pass

        # External / non-Discord matches stored in match_records
        try:
            cur.execute(
                f"SELECT json_deck_data_winner, json_deck_data_loser FROM match_records "
                f"WHERE {_DECK_NOT_EMPTY} AND source != 'Discord' AND source IS NOT NULL"
            )
            _tally(cur.fetchall())
        except sqlite3.OperationalError:
            pass

        # Dedicated external_matches table
        try:
            cur.execute(
                f"SELECT json_deck_data_winner, json_deck_data_loser FROM external_matches "
                f"WHERE {_DECK_NOT_EMPTY}"
            )
            _tally(cur.fetchall())
        except sqlite3.OperationalError:
            pass

        conn.close()
    except Exception:
        return None

    total = wins + losses
    if total == 0:
        return None
    return {"wins": wins, "losses": losses, "total": total, "win_rate": round(wins / total * 100, 1)}


@og_preview_bp.route("/player/<player_id>")
def og_player(player_id: str):
    """OG preview for a player profile page."""
    if not _is_bot():
        return _serve_spa()

    try:
        elo_repo = EloRepository()
        player_service = PlayerService()

        elo_data = elo_repo.get_user_elo(player_id)
        standings = elo_repo.get_all_standings()
        player_row = next((p for p in standings if str(p["user_id"]) == str(player_id)), None)

        name = player_row["display_name"] if player_row else "Player"
        elo = player_row["online_elo"] if player_row else 1500

        stats = player_service.get_player_stats(player_id)
        wins = stats["wins"] if stats else 0
        losses = stats["losses"] if stats else 0
        win_rate = stats["win_rate"] if stats else None

        parts = [f"ELO: {elo}", f"{wins}W – {losses}L"]
        if win_rate is not None and (wins + losses) > 0:
            parts.append(f"{win_rate:.1f}% win rate")

        description = " | ".join(parts)
    except Exception:
        name = "Player"
        description = "Sorcery: Contested Realm player profile"

    return _og_html(
        title=f"{name} — Sorcerers Summit",
        description=description,
        url=f"{SITE_URL}/player/{player_id}",
    )


@og_preview_bp.route("/elo")
def og_elo():
    """OG preview for the ELO leaderboard page."""
    if not _is_bot():
        return _serve_spa()

    try:
        elo_repo = EloRepository()
        standings = elo_repo.get_all_standings()
        count = len(standings) if standings else 0
        if standings:
            top = standings[0]
            top_name = top.get("display_name", "")
            top_elo = top.get("online_elo", 0)
            description = f"{count} ranked players | #1: {top_name} ({top_elo} ELO)"
        else:
            description = f"{count} ranked players on the Sorcery: Contested Realm leaderboard"
    except Exception:
        description = "ELO leaderboard for Sorcery: Contested Realm — see top ranked players"

    return _og_html(
        title="ELO Leaderboard — Sorcerers Summit",
        description=description,
        url=f"{SITE_URL}/elo",
    )


@og_preview_bp.route("/avatars")
def og_avatars_list():
    """OG preview for the avatars listing page."""
    if not _is_bot():
        return _serve_spa()

    return _og_html(
        title="Avatar Stats — Sorcerers Summit",
        description="Win rates, match counts, and top players for every avatar in Sorcery: Contested Realm",
        url=f"{SITE_URL}/avatars",
    )


@og_preview_bp.route("/avatar/<path:avatar_name>")
def og_avatar_detail(avatar_name: str):
    """OG preview for a specific avatar's stats page."""
    if not _is_bot():
        return _serve_spa()

    stats = _get_avatar_stats(avatar_name)
    image = _resolve_avatar_image_url(avatar_name)

    if stats:
        description = (
            f"{stats['total']} matches | {stats['win_rate']}% win rate "
            f"({stats['wins']}W – {stats['losses']}L)"
        )
    else:
        description = f"Match stats and win rate for {avatar_name} in Sorcery: Contested Realm"

    return _og_html(
        title=f"{avatar_name} — Sorcerers Summit",
        description=description,
        url=f"{SITE_URL}/avatar/{avatar_name}",
        image=image,
    )


@og_preview_bp.route("/card/<path:card_name>")
def og_card_detail(card_name: str):
    """OG preview for a specific card's stats page."""
    if not _is_bot():
        return _serve_spa()

    try:
        catalog = CardCatalogRepository()
        card = catalog.get_card(card_name)
        if card:
            parts = []
            if card.get("card_type"):
                parts.append(card["card_type"])
            if card.get("elements"):
                parts.append(card["elements"])
            if card.get("rarity"):
                parts.append(card["rarity"])
            description = " · ".join(parts) if parts else "Card stats for Sorcery: Contested Realm"
            title = card["name"]
        else:
            title = card_name
            description = "Card stats for Sorcery: Contested Realm"
    except Exception:
        title = card_name
        description = "Card stats for Sorcery: Contested Realm"

    return _og_html(
        title=f"{title} — Sorcerers Summit",
        description=description,
        url=f"{SITE_URL}/card/{card_name}",
    )
