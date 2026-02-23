"""Page routes for HTML rendering."""

import os
from flask import Blueprint, render_template, redirect, url_for, session, request

from webapp_config import AVATAR_IMAGES_DIR, TOP_8_DIR
from utils.auth import is_admin
from utils.formatting import format_event_name
from repositories.fart import FartRepository
from repositories.events import EventRepository
from repositories.community import CommunityRepository

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def home():
    """Home page."""
    return render_template("pages/index.html")


@pages_bp.route("/about")
def about():
    """About page."""
    return render_template("pages/about.html")


@pages_bp.route("/community")
def community():
    """Community links page."""
    repo = CommunityRepository()
    return render_template(
        "pages/community.html",
        discord_servers=repo.get_discord_servers(),
        websites=repo.get_websites(),
    )


@pages_bp.route("/help")
def help_page():
    """Help and documentation page."""
    return render_template("pages/help.html")


@pages_bp.route("/deck-help")
def deck_help():
    """Deck help and resources page."""
    return render_template("pages/deck_help.html")


@pages_bp.route("/secret-fart-leaderboard")
def fart_leaderboard():
    """Secret fart leaderboard - Easter egg page."""
    try:
        repo = FartRepository()
        leaderboard_data = repo.get_leaderboard()
        return render_template("pages/fart_leaderboard.html", leaderboard=leaderboard_data)
    except Exception as e:
        print(f"Error loading fart leaderboard: {e}")
        return render_template("pages/fart_leaderboard.html", leaderboard=[])


@pages_bp.route("/avatars")
def avatars():
    """Avatar stats page."""
    avatar_image_files = []
    if AVATAR_IMAGES_DIR.exists():
        avatar_image_files = [
            f for f in os.listdir(AVATAR_IMAGES_DIR)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ]
    return render_template("pages/avatars.html", avatar_image_files=avatar_image_files, user_is_admin=is_admin())


@pages_bp.route("/cards")
def cards():
    """Card winrates page - restricted to allowed Discord users."""
    if not is_admin():
        if session.get("user_id") is None:
            return redirect(url_for("auth.discord_login"))
        return render_template(
            "pages/error.html", error="You don't have permission to view this page."
        ), 403
    return render_template("pages/cards.html")


@pages_bp.route("/live-popular-cards")
def live_popular_cards():
    """Live popular cards page - restricted to allowed Discord users."""
    if not is_admin():
        if session.get("user_id") is None:
            return redirect(url_for("auth.discord_login"))
        return render_template(
            "pages/error.html", error="You don't have permission to view this page."
        ), 403
    return render_template("pages/live_popular_cards.html")


@pages_bp.route("/elements")
def elements():
    """Elemental winrates page."""
    return render_template("pages/elements.html")


@pages_bp.route("/elo")
def elo():
    """ELO leaderboards page."""
    return render_template("pages/elo.html")


@pages_bp.route("/elo/global")
def elo_global():
    """Global ELO leaderboard."""
    return render_template("pages/elo_global.html")


@pages_bp.route("/elo/server/<server_id>")
def elo_server(server_id):
    """Server-specific ELO leaderboard."""
    server_names = {
        "sorcerers-summit": "Sorcerers Summit",
        "tts-league": "TTS League",
        "competitive": "Competitive Server",
    }
    server_name = server_names.get(server_id, f"Server ({server_id})")
    return render_template(
        "pages/elo_server.html", server_id=server_id, server_name=server_name
    )


@pages_bp.route("/match-history")
def match_history():
    """Match history page - shows matches from last 24 hours."""
    return render_template("pages/match_history.html")


@pages_bp.route("/top-8")
def top_8():
    """Top 8 decks by event page - lists all events."""
    repo = EventRepository()
    events = repo.get_all_events()
    return render_template("pages/top_8.html", events=events)


@pages_bp.route("/top-8/<event_folder>")
def top_8_event(event_folder):
    """Display Top 8 decks for a specific event."""
    repo = EventRepository()

    decks = repo.get_event_decks(event_folder)
    if decks is None:
        return "Event not found", 404

    stats = repo.get_event_stats(event_folder)
    element_stats = repo.get_event_element_stats(event_folder)

    return render_template(
        "pages/top_8_event.html",
        event_name=format_event_name(event_folder),
        event_folder=event_folder,
        top8_decks=decks["top8_decks"],
        all_decks=decks["all_decks"],
        card_data=stats["card_data"] if stats else [],
        element_data=stats["element_data"] if stats else [],
        element_stats=element_stats,
    )


@pages_bp.route("/stats")
def stats():
    """Statistics page - lists all events with CSV data."""
    repo = EventRepository()
    events = repo.get_events_with_stats()
    return render_template("pages/stats.html", events=events)


@pages_bp.route("/stats/<event_folder>")
def stats_event(event_folder):
    """Display statistics for a specific event."""
    repo = EventRepository()

    stats = repo.get_event_stats(event_folder)
    if stats is None:
        return "Event not found", 404

    element_stats = repo.get_event_element_stats(event_folder)

    return render_template(
        "pages/stats_event.html",
        event_name=format_event_name(event_folder),
        event_folder=event_folder,
        element_data=stats["element_data"],
        card_data=stats["card_data"],
        element_stats=element_stats,
    )


@pages_bp.route("/player/<player_id>")
def player_profile(player_id):
    """Player profile page."""
    return render_template("pages/player.html", player_id=player_id)


@pages_bp.route("/avatar/<avatar_name>")
def avatar_profile(avatar_name):
    """Avatar profile page."""
    from urllib.parse import unquote
    avatar_name = unquote(avatar_name)
    return render_template("pages/avatar.html", avatar_name=avatar_name)


@pages_bp.route("/card/<card_name>")
def card_profile(card_name):
    """Card profile page - restricted to allowed Discord users."""
    from urllib.parse import unquote
    card_name = unquote(card_name)

    if not is_admin():
        if session.get("user_id") is None:
            return redirect(url_for("auth.discord_login"))
        return render_template(
            "pages/error.html", error="You don't have permission to view this page."
        ), 403

    return render_template("pages/card.html", card_name=card_name)


@pages_bp.route("/deck-snapshot/<int:match_id>/<player_id>")
def deck_snapshot(match_id, player_id):
    """Deck snapshot page."""
    logged_in_user_id = session.get("user_id")
    is_owner = logged_in_user_id is not None and str(logged_in_user_id) == str(player_id)

    # Admins can view any deck snapshot
    if not is_owner and not is_admin():
        return render_template(
            "pages/error.html", error="You can only view your own deck snapshots"
        ), 403

    return render_template(
        "pages/deck_snapshot.html", match_id=match_id, player_id=player_id
    )
