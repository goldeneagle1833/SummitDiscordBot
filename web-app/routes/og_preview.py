"""Open Graph preview routes for Discord/social media link embeds.

Discord and other social platforms don't execute JavaScript, so they can't
read meta tags set by the React SPA. These routes detect bot user agents
(via Nginx forwarding) and return minimal HTML with dynamic OG meta tags.

For regular users, Nginx serves the React SPA directly — these routes
are only hit by crawlers.
"""

import logging
import re
import os

from flask import Blueprint, request

from repositories.events import EventRepository
from repositories.deck_rec_repo import DeckRecRepository
from utils.formatting import format_event_name
from webapp_config import AVATAR_IMAGES_DIR

logger = logging.getLogger(__name__)

og_preview_bp = Blueprint("og_preview", __name__)

SITE_URL = "https://sorcererssummit.com"
SITE_NAME = "Sorcerers Summit"
DEFAULT_IMAGE = f"{SITE_URL}/static/images/favicon.png"
THEME_COLOR = "#1a1a2e"


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
    return _og_html(
        title="Deck Recommendations — Sorcerers Summit",
        description="Browse tournament-proven archetypes and community deck recommendations for Sorcery: Contested Realm",
        url=f"{SITE_URL}/deck-rec",
    )


@og_preview_bp.route("/deck-rec/<deck_id>")
def og_deck_detail(deck_id: str):
    """OG preview for a specific deck recommendation page."""
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
