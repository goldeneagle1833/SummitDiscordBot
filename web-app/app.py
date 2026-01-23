"""
Summit Web Application - A lightweight Flask web app
"""

from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import sqlite3
import os
import json
import sys
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlencode
from functools import wraps

# Load environment variables from discord-bot/.env (shared config)
_env_path = Path(__file__).parent.parent / "discord-bot" / ".env"
load_dotenv(_env_path)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add discord-bot to path for shared config
_bot_path = str(Path(__file__).parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.insert(0, _bot_path)

# Add SorceryAI to path
_sorcery_ai_path = str(Path(__file__).parent.parent / "SorceryAI")
if _sorcery_ai_path not in sys.path:
    sys.path.insert(0, _sorcery_ai_path)

app = Flask(__name__)

# Session configuration
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

# Discord OAuth configuration
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.environ.get(
    "DISCORD_REDIRECT_URI", "http://localhost:5000/auth/discord/callback"
)

# API Key configuration for external integrations
# Support both single API_KEY and multiple API_KEYS (comma-separated)
API_KEYS_ENV = os.environ.get("API_KEYS", os.environ.get("API_KEY", ""))
VALID_API_KEYS = [key.strip() for key in API_KEYS_ENV.split(",") if key.strip()]

# Initialize SorceryAI components (lazy load)
_rules_retriever = None
_rules_generator = None


def require_api_key(f):
    """Decorator to require API key authentication for endpoints"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key in headers
        provided_key = request.headers.get("X-API-Key") or request.headers.get(
            "Authorization"
        )

        # Support "Bearer <key>" format
        if provided_key and provided_key.startswith("Bearer "):
            provided_key = provided_key[7:]

        # Validate API key
        if not VALID_API_KEYS:
            logger.error("No API keys configured in environment")
            return jsonify({"error": "API authentication not configured"}), 500

        if not provided_key or provided_key not in VALID_API_KEYS:
            logger.warning(
                f"Unauthorized API access attempt from {request.remote_addr}"
            )
            return jsonify({"error": "Invalid or missing API key"}), 401

        return f(*args, **kwargs)

    return decorated_function


def get_rules_assistant():
    """Lazy load rules assistant components"""
    global _rules_retriever, _rules_generator

    if _rules_retriever is None or _rules_generator is None:
        try:
            from core.retriever import RulesRetriever
            from core.generator import RulesGenerator

            _rules_retriever = RulesRetriever()
            _rules_generator = RulesGenerator()
            _rules_generator.ensure_initialized()
        except Exception as e:
            logger.error(f"Failed to initialize Rules Assistant: {e}", exc_info=True)
            raise

    return _rules_retriever, _rules_generator


# Path to top-8 event data
TOP_8_DIR = Path(__file__).parent / "top-8-decks-by-event"


def extract_year_from_name(name):
    """Extract year from event name for sorting. Returns 0 if no year found."""
    import re
    # Look for 4-digit years (2020-2029)
    match = re.search(r'20(2[0-9])', name)
    if match:
        return int("20" + match.group(1))
    # Check for 2-digit years like "25" that likely mean 2025
    match = re.search(r'(?<!\d)(2[3-9])(?!\d)', name)
    if match:
        return int("20" + match.group(1))
    return 0


def format_event_name(folder_name):
    """Format event folder name into a readable display name"""
    # Custom mappings for special cases
    name_mappings = {
        "ColumbusExplor2025": "Columbus Explorer 2025",
        "CortCup2024Stats": "Cort Cup 2024",
        "Explorer96": "Explorer 9.6",
        "GenCon2023Stats": "Gen Con 2023",
        "GenCon2024Stats": "Gen Con 2024",
        "Gencon2025": "Gen Con 2025",
        "OchoaDecklists": "Ochoa Decklists",
        "SCGCON2025": "SCG CON 2025",
        "Season6TTSLeage": "Season 6 TTS League",
        "SorcerersSummit": "Sorcerers Summit",
        "SORCERY CON": "Sorcery Con",
        "SorceryCon 2024 stats": "Sorcery Con 2024",
        "SorceryFest2025": "Sorcery Fest 2025",
        "SS2": "Sorcerers Summit 2",
        "TTSLeague2023champions": "TTS League 2023 Champions",
        "TTSLeagueS3": "TTS League Season 3",
        "TTSLeagueS7topCut": "TTS League Season 7 Top Cut",
        "UnlandCup25": "Unland Cup 2025",
    }

    # Return custom mapping if available
    if folder_name in name_mappings:
        return name_mappings[folder_name]

    # Otherwise, do basic formatting
    return folder_name.replace("_", " ").replace("-", " ").title()


@app.route("/")
def home():
    """Home page"""
    return render_template("pages/index.html")


@app.route("/about")
def about():
    """About page"""
    return render_template("pages/about.html")


# =============================================================================
# Discord OAuth Routes
# =============================================================================


def get_current_user():
    """Get the currently logged in user from session, or None"""
    if "user_id" in session:
        return {
            "id": session["user_id"],
            "username": session.get("username"),
            "avatar": session.get("avatar"),
        }
    return None


@app.context_processor
def inject_user():
    """Make current user available to all templates"""
    return {"current_user": get_current_user()}


@app.route("/auth/discord")
def auth_discord():
    """Redirect user to Discord OAuth authorization"""
    if not DISCORD_CLIENT_ID:
        logger.error("DISCORD_CLIENT_ID not configured")
        return "OAuth not configured", 500

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
    }
    auth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return redirect(auth_url)


@app.route("/auth/discord/callback")
def auth_discord_callback():
    """Handle Discord OAuth callback"""
    error = request.args.get("error")
    if error:
        logger.error(f"Discord OAuth error: {error}")
        return redirect(url_for("home"))

    code = request.args.get("code")
    if not code:
        logger.error("No code received from Discord")
        return redirect(url_for("home"))

    # Exchange code for access token
    token_url = "https://discord.com/api/oauth2/token"
    token_data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
    }

    try:
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get Discord token: {e}")
        return redirect(url_for("home"))

    access_token = tokens.get("access_token")
    if not access_token:
        logger.error("No access token in Discord response")
        return redirect(url_for("home"))

    # Get user info from Discord
    user_url = "https://discord.com/api/users/@me"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        user_response = requests.get(user_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get Discord user info: {e}")
        return redirect(url_for("home"))

    # Store user info in session
    session["user_id"] = int(user_data["id"])
    session["username"] = user_data["username"]
    session["avatar"] = user_data.get("avatar")

    logger.info(f"User {user_data['username']} (ID: {user_data['id']}) logged in")

    # Redirect to home or previous page
    return redirect(url_for("home"))


@app.route("/auth/logout")
def auth_logout():
    """Clear session and log out user"""
    username = session.get("username", "Unknown")
    session.clear()
    logger.info(f"User {username} logged out")
    return redirect(url_for("home"))


# =============================================================================
# End Discord OAuth Routes
# =============================================================================


@app.route("/secret-fart-leaderboard")
def fart_leaderboard():
    """Secret fart leaderboard - Easter egg page"""
    try:
        conn = sqlite3.connect(
            Path(__file__).parent.parent / "discord-bot" / "fart_scores.db"
        )
        cursor = conn.cursor()

        cursor.execute("""
            SELECT user_id, user_display_name, score, date_last_updated
            FROM fart_scores
            ORDER BY score DESC
        """)

        leaderboard_data = []
        for rank, row in enumerate(cursor.fetchall(), start=1):
            leaderboard_data.append(
                {
                    "rank": rank,
                    "user_id": row[0],
                    "username": row[1],
                    "score": row[2],
                    "last_updated": row[3],
                }
            )

        conn.close()
        return render_template(
            "pages/fart_leaderboard.html", leaderboard=leaderboard_data
        )
    except Exception as e:
        print(f"Error loading fart leaderboard: {e}")
        return render_template("pages/fart_leaderboard.html", leaderboard=[])


@app.route("/avatars")
def avatars():
    """Avatar stats page"""
    # Get list of avatar image files
    avatar_imgs_dir = os.path.join(app.root_path, "templates", "avatar_imgs")
    avatar_image_files = []
    if os.path.exists(avatar_imgs_dir):
        avatar_image_files = [
            f
            for f in os.listdir(avatar_imgs_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ]
    return render_template("pages/avatars.html", avatar_image_files=avatar_image_files)


@app.route("/elo")
def elo():
    """ELO leaderboards page"""
    return render_template("pages/elo.html")


@app.route("/elo/global")
def elo_global():
    """Global ELO leaderboard"""
    return render_template("pages/elo_global.html")


@app.route("/elo/server/<server_id>")
def elo_server(server_id):
    """Server-specific ELO leaderboard"""
    # Mock server names for demonstration
    server_names = {
        "sorcerers-summit": "Sorcerers Summit",
        "tts-league": "TTS League",
        "competitive": "Competitive Server",
    }
    server_name = server_names.get(server_id, f"Server ({server_id})")
    return render_template(
        "pages/elo_server.html", server_id=server_id, server_name=server_name
    )


@app.route("/match-history")
def match_history():
    """Match history page - shows matches from last 24 hours"""
    return render_template("pages/match_history.html")


@app.route("/api/match-history/available-dates")
def match_history_available_dates():
    """API endpoint to get dates that have match data"""
    try:
        conn = sqlite3.connect("../discord-bot/match_records.db")
        cur = conn.cursor()

        # Get all unique dates that have matches
        cur.execute("""
            SELECT DISTINCT date(timestamp) as match_date
            FROM match_records
            WHERE timestamp IS NOT NULL
            ORDER BY match_date DESC
        """)

        dates = [row[0] for row in cur.fetchall()]
        conn.close()
        return jsonify(dates)

    except Exception as e:
        logger.error(f"Error fetching available dates: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/match-history")
def match_history_api():
    """API endpoint for match history data"""
    try:
        conn = sqlite3.connect("../discord-bot/match_records.db")
        cur = conn.cursor()

        # Get optional date parameter (format: YYYY-MM-DD)
        selected_date = request.args.get("date")

        if selected_date:
            # Fetch matches for specific date
            cur.execute(
                """
                SELECT
                    rowid as match_id,
                    winner_display_name,
                    winner_elo_change,
                    losser_display_name,
                    loser_elo_change,
                    match_time,
                    timestamp,
                    winner_id,
                    losser_id
                FROM match_records
                WHERE date(timestamp) = ?
                ORDER BY rowid DESC
            """,
                (selected_date,),
            )
        else:
            # Fetch matches from last 24 hours (default)
            cur.execute("""
                SELECT
                    rowid as match_id,
                    winner_display_name,
                    winner_elo_change,
                    losser_display_name,
                    loser_elo_change,
                    match_time,
                    timestamp,
                    winner_id,
                    losser_id
                FROM match_records
                WHERE timestamp >= datetime('now', '-24 hours')
                ORDER BY rowid DESC
            """)

        matches = []
        for row in cur.fetchall():
            matches.append(
                {
                    "match_id": row[0],
                    "winner": row[1] or "Unknown",
                    "winner_elo_change": row[2] or 0,
                    "loser": row[3] or "Unknown",
                    "loser_elo_change": row[4] or 0,
                    "match_time": row[5] or 0,
                    "timestamp": row[6],
                    "winner_id": row[7],
                    "loser_id": row[8],
                }
            )

        conn.close()
        return jsonify(matches)

    except Exception as e:
        logger.error(f"Error fetching match history: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/deck-help")
def deck_help():
    """Deck help and resources page"""
    return render_template("pages/deck_help.html")


@app.route("/top-8")
def top_8():
    """Top 8 decks by event page - lists all events"""
    events = []

    if TOP_8_DIR.exists():
        for folder in TOP_8_DIR.iterdir():
            if folder.is_dir():
                # Look for JSON files in the folder
                json_files = list(folder.glob("*.json"))
                top8_json = None
                full_json = None

                # Find top8 and full event JSON files
                for json_file in json_files:
                    if (
                        "top8" in json_file.name.lower()
                        or "top 8" in json_file.name.lower()
                    ):
                        top8_json = json_file
                    elif json_file.name.lower().startswith(folder.name.lower()):
                        full_json = json_file

                # Use whichever JSON we found
                json_path = top8_json or full_json

                if json_path:
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            player_count = len(data)

                            events.append(
                                {
                                    "folder": folder.name,
                                    "name": format_event_name(folder.name),
                                    "player_count": player_count,
                                    "has_top8": top8_json is not None,
                                    "has_full": full_json is not None,
                                }
                            )
                    except Exception as e:
                        print(f"Error loading {json_path}: {e}")

    # Sort by year (descending), events without dates go last
    events.sort(key=lambda e: (extract_year_from_name(e["name"]) > 0, extract_year_from_name(e["name"])), reverse=True)

    return render_template("pages/top_8.html", events=events)


@app.route("/top-8/<event_folder>")
def top_8_event(event_folder):
    """Display Top 8 decks for a specific event"""
    event_path = TOP_8_DIR / event_folder

    if not event_path.exists():
        return "Event not found", 404

    # Look for JSON files
    json_files = list(event_path.glob("*.json"))
    top8_json = None
    full_json = None

    for json_file in json_files:
        if "top8" in json_file.name.lower() or "top 8" in json_file.name.lower():
            top8_json = json_file
        elif json_file.name.lower().startswith(event_folder.lower()):
            full_json = json_file

    top8_decks = []
    all_decks = []

    # Load top 8 decks
    if top8_json:
        try:
            with open(top8_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                for deck in data[:8]:  # Ensure only top 8
                    top8_decks.append(
                        {
                            "player": deck.get("username", "Unknown"),
                            "avatar": deck.get("avatar", [{}])[0].get(
                                "name", "Unknown"
                            ),
                            "deck_name": deck.get("name", "Unnamed Deck"),
                            "deck_id": deck.get("id", ""),
                        }
                    )
        except Exception as e:
            print(f"Error loading top 8: {e}")

    # Load all participants if available
    if full_json and full_json != top8_json:
        try:
            with open(full_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                for deck in data:
                    all_decks.append(
                        {
                            "player": deck.get("username", "Unknown"),
                            "avatar": deck.get("avatar", [{}])[0].get(
                                "name", "Unknown"
                            ),
                            "deck_name": deck.get("name", "Unnamed Deck"),
                            "deck_id": deck.get("id", ""),
                        }
                    )
        except Exception as e:
            print(f"Error loading full event: {e}")

    return render_template(
        "pages/top_8_event.html",
        event_name=format_event_name(event_folder),
        event_folder=event_folder,
        top8_decks=top8_decks,
        all_decks=all_decks,
    )


@app.route("/stats")
def stats():
    """Statistics page - lists all events with CSV data"""
    events = []

    if TOP_8_DIR.exists():
        for folder in TOP_8_DIR.iterdir():
            if folder.is_dir():
                # Look for CSV files in the folder
                csv_files = list(folder.glob("*.csv"))
                elements_csv = None
                cards_csv = None

                for csv_file in csv_files:
                    if "element" in csv_file.name.lower():
                        elements_csv = csv_file
                    elif not any(
                        x in csv_file.name.lower() for x in ["element", "top8", "top 8"]
                    ):
                        cards_csv = csv_file

                if elements_csv or cards_csv:
                    events.append(
                        {
                            "folder": folder.name,
                            "name": format_event_name(folder.name),
                            "has_elements": elements_csv is not None,
                            "has_cards": cards_csv is not None,
                        }
                    )

    # Sort by year (descending), events without dates go last
    events.sort(key=lambda e: (extract_year_from_name(e["name"]) > 0, extract_year_from_name(e["name"])), reverse=True)

    return render_template("pages/stats.html", events=events)


@app.route("/stats/<event_folder>")
def stats_event(event_folder):
    """Display statistics for a specific event"""
    import csv

    event_path = TOP_8_DIR / event_folder

    if not event_path.exists():
        return "Event not found", 404

    # Look for CSV files
    csv_files = list(event_path.glob("*.csv"))
    elements_csv = None
    cards_csv = None

    for csv_file in csv_files:
        if "element" in csv_file.name.lower():
            elements_csv = csv_file
        elif not any(x in csv_file.name.lower() for x in ["element", "top8", "top 8"]):
            cards_csv = csv_file

    element_data = []
    card_data = []

    # Load element distribution data
    if elements_csv:
        try:
            with open(elements_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    element_data.append(
                        {
                            "elements": row.get("Deck Elements", "").strip("\"()' "),
                            "count": row.get(" Count", row.get("Count", "0")),
                        }
                    )
        except Exception as e:
            print(f"Error loading elements CSV: {e}")

    # Load card statistics data
    if cards_csv:
        try:
            with open(cards_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Only include cards that were actually played
                    count = int(row.get("Count", 0))
                    if count > 0:
                        card_data.append(
                            {
                                "name": row.get("Name", "Unknown"),
                                "type": row.get("Type", "Unknown"),
                                "element": row.get("Element", "Unknown"),
                                "count": count,
                                "rarity": row.get("Rarity", "Unknown"),
                                "avg_played": row.get("Average_Played", "0"),
                                "deck_percent": row.get(
                                    "Percent_of_Decks_with_at_least_one_copy", "0"
                                ),
                            }
                        )
            # Sort by count descending
            card_data.sort(key=lambda x: x["count"], reverse=True)
        except Exception as e:
            print(f"Error loading cards CSV: {e}")

    return render_template(
        "pages/stats_event.html",
        event_name=format_event_name(event_folder),
        event_folder=event_folder,
        element_data=element_data,
        card_data=card_data,
    )


@app.route("/help")
def help_page():
    """Help and documentation page"""
    return render_template("pages/help.html")


@app.route("/api/status")
def api_status():
    """Simple API endpoint to check if the server is running"""
    return jsonify({"status": "online", "message": "Summit Web App is running!"})


@app.route("/api/report-match", methods=["POST"])
@require_api_key
def report_match():
    """
    API endpoint to report match results from external applications.

    Required fields:
    - winner_name: Display name of the winner
    - winner_id: Discord ID of the winner
    - loser_name: Display name of the loser
    - loser_id: Discord ID of the loser

    Optional fields:
    - first_player: 'y' or 'n' to indicate who went first (default: 'n')
    - match_time: Duration of match in minutes (default: 0)
    - winner_deck_url: URL to winner's deck on Curiosa
    - loser_deck_url: URL to loser's deck on Curiosa
    - match_comment: Additional notes about the match
    - reporter_id: Discord ID of the person reporting (defaults to winner_id)

    Returns:
    - match_id: The ID of the created match record
    - winner_elo: New ELO rating for winner
    - loser_elo: New ELO rating for loser
    - winner_elo_change: ELO change for winner
    - loser_elo_change: ELO change for loser
    """
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ["winner_name", "winner_id", "loser_name", "loser_id"]
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify(
                {"error": "Missing required fields", "missing": missing_fields}
            ), 400

        # Extract required fields
        winner_name = str(data["winner_name"])
        winner_id = int(data["winner_id"])
        loser_name = str(data["loser_name"])
        loser_id = int(data["loser_id"])

        # Extract optional fields with defaults
        first_player = str(data.get("first_player", "n")).lower()
        match_time = int(data.get("match_time", 0))
        winner_deck_url = data.get("winner_deck_url", "No URL provided")
        loser_deck_url = data.get("loser_deck_url", "No URL provided")
        match_comment = data.get("match_comment", "")
        reporter_id = int(data.get("reporter_id", winner_id))

        # Validate first_player value
        if first_player not in ["y", "n"]:
            return jsonify(
                {
                    "error": "Invalid value for first_player",
                    "detail": "Must be 'y' or 'n'",
                }
            ), 400

        # Add discord-bot to path to import database utilities
        _bot_path = str(Path(__file__).parent.parent / "discord-bot")
        if _bot_path not in sys.path:
            sys.path.insert(0, _bot_path)

        # Import database functions from discord-bot
        from utils.database import winner_report
        import asyncio

        # Report the match (this will update ELO automatically)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            match_id, _, _ = loop.run_until_complete(
                winner_report(
                    reporter_id=reporter_id,
                    user_id=winner_id,
                    user_display_name=winner_name,
                    did_win=True,
                    opponent_id=loser_id,
                    opponent_display_name=loser_name,
                    first_player=first_player,
                    match_time=match_time,
                    curiosa_link=winner_deck_url,  # Legacy parameter
                    match_comment=match_comment,
                    interaction_user_id=winner_id,
                    interaction_global=winner_name,
                    winner_deck_url=winner_deck_url,
                    loser_deck_url=loser_deck_url,
                )
            )
        finally:
            loop.close()

        # Get updated ELO ratings
        from utils.database import get_user_elo

        winner_elo = get_user_elo(winner_id)
        loser_elo = get_user_elo(loser_id)

        # Get ELO changes from the match record
        conn = sqlite3.connect("../discord-bot/match_records.db")
        cur = conn.cursor()
        cur.execute(
            "SELECT winner_elo_change, loser_elo_change FROM match_records WHERE match_id = ?",
            (match_id,),
        )
        row = cur.fetchone()
        conn.close()

        winner_elo_change = row[0] if row else 0
        loser_elo_change = row[1] if row else 0

        logger.info(
            f"Match reported via API: {winner_name} (ID: {winner_id}) defeated "
            f"{loser_name} (ID: {loser_id}), Match ID: {match_id}"
        )

        return jsonify(
            {
                "success": True,
                "match_id": match_id,
                "winner": {
                    "name": winner_name,
                    "id": winner_id,
                    "elo": winner_elo,
                    "elo_change": winner_elo_change,
                },
                "loser": {
                    "name": loser_name,
                    "id": loser_id,
                    "elo": loser_elo,
                    "elo_change": loser_elo_change,
                },
            }
        ), 201

    except ValueError as e:
        return jsonify({"error": "Invalid data type", "detail": str(e)}), 400
    except Exception as e:
        logger.error(f"Error reporting match via API: {e}", exc_info=True)
        return jsonify({"error": "Failed to report match", "detail": str(e)}), 500


# Leaderboard API endpoint
@app.route("/api/leaderboard")
def leaderboard():
    # Get ELO standings
    conn = sqlite3.connect("../discord-bot/elo.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, user_display_name, elo
        FROM overall_standings
        ORDER BY elo DESC
    """)
    rows = cur.fetchall()
    conn.close()

    # Get win/loss records from match_records
    conn = sqlite3.connect("../discord-bot/match_records.db")
    cur = conn.cursor()

    leaderboard_data = []
    for row in rows:
        user_id = row[0]
        # Count wins
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE winner_id = ?", (user_id,)
        )
        wins = cur.fetchone()[0]
        # Count losses
        cur.execute(
            "SELECT COUNT(*) FROM match_records WHERE losser_id = ?", (user_id,)
        )
        losses = cur.fetchone()[0]

        leaderboard_data.append(
            {
                "id": str(row[0]),
                "name": row[1],
                "elo": row[2],
                "wins": wins,
                "losses": losses,
            }
        )

    conn.close()
    return jsonify(leaderboard_data)


@app.route("/api/elo-distribution")
def elo_distribution():
    """Get ELO distribution across bands"""
    conn = sqlite3.connect("../discord-bot/elo.db")
    cur = conn.cursor()
    cur.execute("SELECT elo FROM overall_standings")
    elos = [row[0] for row in cur.fetchall()]
    conn.close()

    total_players = len(elos)

    if total_players == 0:
        return jsonify({"increments": [], "offset": []})

    # Define 100pt increments (1200-1299, 1300-1399, etc.)
    increments = []
    for lower in range(1100, 2100, 100):
        upper = lower + 99
        count = sum(1 for elo in elos if lower <= elo <= upper)
        percentage = (count / total_players * 100) if count > 0 else 0
        increments.append(
            {
                "range": f"{lower}-{upper}",
                "count": count,
                "percentage": round(percentage, 2),
            }
        )

    # Add 2000+ bucket
    count_2000_plus = sum(1 for elo in elos if elo >= 2000)
    percentage_2000_plus = (
        (count_2000_plus / total_players * 100) if count_2000_plus > 0 else 0
    )
    increments.append(
        {
            "range": "2000+",
            "count": count_2000_plus,
            "percentage": round(percentage_2000_plus, 2),
        }
    )

    # Define 100pt offset (1050-1149, 1150-1249, etc.)
    offset = []
    for lower in range(1050, 2000, 100):
        upper = lower + 99
        count = sum(1 for elo in elos if lower <= elo <= upper)
        percentage = (count / total_players * 100) if count > 0 else 0
        offset.append(
            {
                "range": f"{lower}-{upper}",
                "count": count,
                "percentage": round(percentage, 2),
            }
        )

    # Add 1950+ bucket
    count_1950_plus = sum(1 for elo in elos if elo >= 1950)
    percentage_1950_plus = (
        (count_1950_plus / total_players * 100) if count_1950_plus > 0 else 0
    )
    offset.append(
        {
            "range": "1950+",
            "count": count_1950_plus,
            "percentage": round(percentage_1950_plus, 2),
        }
    )

    return jsonify(
        {
            "increments": list(reversed(increments)),  # Reverse to show highest first
            "offset": list(reversed(offset)),
            "total_players": total_players,
        }
    )


# Player profile page
@app.route("/player/<player_id>")
def player_profile(player_id):
    return render_template("pages/player.html", player_id=player_id)


# Avatar profile page
@app.route("/avatar/<avatar_name>")
def avatar_profile(avatar_name):
    from urllib.parse import unquote

    avatar_name = unquote(avatar_name)
    return render_template("pages/avatar.html", avatar_name=avatar_name)


# Deck snapshot page
@app.route("/deck-snapshot/<int:match_id>/<player_id>")
def deck_snapshot(match_id, player_id):
    # Check if logged-in user is the profile owner
    logged_in_user_id = session.get("user_id")
    is_owner = logged_in_user_id is not None and str(logged_in_user_id) == str(
        player_id
    )

    # Auto-set owner to true on localhost for development
    if request.host.startswith("localhost") or request.host.startswith("127.0.0.1"):
        is_owner = True

    if not is_owner:
        return render_template(
            "pages/error.html", error="You can only view your own deck snapshots"
        ), 403

    return render_template(
        "pages/deck_snapshot.html", match_id=match_id, player_id=player_id
    )


# Deck snapshot API endpoint
@app.route("/api/deck-snapshot/<int:match_id>/<player_id>")
def deck_snapshot_api(match_id, player_id):
    import json

    # Check if logged-in user is the profile owner
    logged_in_user_id = session.get("user_id")
    is_owner = logged_in_user_id is not None and str(logged_in_user_id) == str(
        player_id
    )

    # Auto-set owner to true on localhost for development
    if request.host.startswith("localhost") or request.host.startswith("127.0.0.1"):
        is_owner = True

    if not is_owner:
        return jsonify({"error": "Unauthorized"}), 403

    # Get the match data
    conn = sqlite3.connect("../discord-bot/match_records.db")
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                winner_id,
                losser_id,
                winner_display_name,
                losser_display_name,
                timestamp,
                json_deck_data,
                json_deck_data_winner,
                json_deck_data_loser
            FROM match_records
            WHERE rowid = ?
        """,
            (match_id,),
        )
        row = cur.fetchone()
    except sqlite3.OperationalError:
        # Fallback to old schema
        cur.execute(
            """
            SELECT
                winner_id,
                losser_id,
                winner_display_name,
                losser_display_name,
                timestamp,
                json_deck_data
            FROM match_records
            WHERE rowid = ?
        """,
            (match_id,),
        )
        row = cur.fetchone()

    conn.close()

    if not row:
        return jsonify({"error": "Match not found"}), 404

    winner_id = str(row[0])
    loser_id = str(row[1])
    winner_name = row[2]
    loser_name = row[3]
    timestamp = row[4]
    old_json_deck = row[5] if len(row) > 5 else None
    winner_json = row[6] if len(row) > 6 else None
    loser_json = row[7] if len(row) > 7 else None

    # Determine if player was winner or loser
    player_id_str = str(player_id)
    if player_id_str == winner_id:
        deck_json = (
            winner_json if winner_json and winner_json != "{}" else old_json_deck
        )
        player_name = winner_name
        result = "Win"
        opponent_name = loser_name
    elif player_id_str == loser_id:
        deck_json = loser_json if loser_json and loser_json != "{}" else old_json_deck
        player_name = loser_name
        result = "Loss"
        opponent_name = winner_name
    else:
        return jsonify({"error": "Player not found in this match"}), 404

    if not deck_json or deck_json == "{}":
        return jsonify({"error": "No deck data available for this match"}), 404

    try:
        deck_data = json.loads(deck_json)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid deck data"}), 500

    return jsonify(
        {
            "match_id": match_id,
            "player_name": player_name,
            "opponent_name": opponent_name,
            "result": result,
            "date": timestamp,
            "deck": deck_data,
        }
    )


# Avatar API endpoint
def generate_pseudonym(player_id):
    """Generate a consistent fun pseudonym from a player ID"""
    import hashlib

    adjectives = [
        "Magical",
        "Sneaky",
        "Brave",
        "Silly",
        "Grumpy",
        "Happy",
        "Sleepy",
        "Dancing",
        "Flying",
        "Jumping",
        "Mystical",
        "Crafty",
        "Clever",
        "Dizzy",
        "Wobbly",
        "Bouncy",
        "Sparkly",
        "Fuzzy",
        "Quirky",
        "Jolly",
        "Wacky",
        "Zany",
        "Goofy",
        "Perky",
        "Spicy",
        "Frosty",
        "Fiery",
        "Stormy",
        "Sunny",
        "Breezy",
        "Shadowy",
        "Glowing",
        "Tiny",
        "Giant",
        "Swift",
        "Lazy",
        "Eager",
        "Shy",
        "Bold",
        "Wild",
        "Gentle",
        "Fierce",
        "Peaceful",
        "Chaotic",
        "Lucky",
        "Clumsy",
        "Graceful",
        "Daring",
    ]

    nouns = [
        "Wizard",
        "Dragon",
        "Penguin",
        "Unicorn",
        "Potato",
        "Banana",
        "Taco",
        "Ninja",
        "Pirate",
        "Robot",
        "Ghost",
        "Phoenix",
        "Turtle",
        "Narwhal",
        "Pancake",
        "Wombat",
        "Llama",
        "Koala",
        "Goblin",
        "Sphinx",
        "Kraken",
        "Yeti",
        "Mermaid",
        "Centaur",
        "Griffin",
        "Chimera",
        "Troll",
        "Dwarf",
        "Elf",
        "Fairy",
        "Gnome",
        "Ogre",
        "Badger",
        "Otter",
        "Panda",
        "Sloth",
        "Walrus",
        "Moose",
        "Raccoon",
        "Squirrel",
        "Platypus",
        "Axolotl",
        "Capybara",
        "Hedgehog",
        "Mango",
        "Coconut",
        "Pickle",
        "Waffle",
    ]

    # Hash the player ID to get consistent indices
    hash_obj = hashlib.md5(str(player_id).encode())
    hash_int = int(hash_obj.hexdigest(), 16)

    # Select adjective and noun based on hash
    adj_index = hash_int % len(adjectives)
    noun_index = (hash_int // len(adjectives)) % len(nouns)

    return f"{adjectives[adj_index]} {nouns[noun_index]}"


@app.route("/api/avatar/<avatar_name>")
def avatar_api(avatar_name):
    import json
    from urllib.parse import unquote

    avatar_name = unquote(avatar_name)

    try:
        conn = sqlite3.connect("../discord-bot/match_records.db")
        cur = conn.cursor()

        # Try to get matches with new columns, fallback to old schema
        try:
            cur.execute(
                """
                SELECT 
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    rowid as match_id
                FROM match_records
                WHERE json_deck_data_winner IS NOT NULL OR json_deck_data_loser IS NOT NULL
                ORDER BY timestamp DESC
            """
            )
            rows = cur.fetchall()
            use_new_columns = True
        except sqlite3.OperationalError:
            # Fallback to old schema
            cur.execute(
                """
                SELECT 
                    winner_id,
                    winner_display_name,
                    losser_id,
                    losser_display_name,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    first_player,
                    match_time,
                    json_deck_data,
                    curiosa_url,
                    rowid as match_id
                FROM match_records
                WHERE json_deck_data IS NOT NULL
                ORDER BY timestamp DESC
            """
            )
            rows = cur.fetchall()
            use_new_columns = False

        conn.close()
    except sqlite3.OperationalError:
        return jsonify({"error": "Database not found"}), 404

    # Filter matches where this avatar was used
    wins_matches = []
    losses_matches = []
    total_wins = 0
    total_losses = 0

    if use_new_columns:
        for row in rows:
            winner_json = row[9]
            loser_json = row[10]

            # Check if avatar is in winner's deck
            avatar_in_winner = False
            if winner_json and winner_json not in ("", "{}"):
                try:
                    deck_data = json.loads(winner_json)
                    if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                        if deck_data["avatar"][0].get("name") == avatar_name:
                            avatar_in_winner = True
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            # Check if avatar is in loser's deck
            avatar_in_loser = False
            if loser_json and loser_json not in ("", "{}"):
                try:
                    deck_data = json.loads(loser_json)
                    if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                        if deck_data["avatar"][0].get("name") == avatar_name:
                            avatar_in_loser = True
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            # Create match object with sanitized names
            match_obj = {
                "match_id": row[13],
                "winner_id": str(row[0]),
                "winner_name": generate_pseudonym(row[0]),
                "loser_id": str(row[2]),
                "loser_name": generate_pseudonym(row[2]),
                "date": row[4],
                "winner_elo_change": row[5] if row[5] else 0,
                "loser_elo_change": row[6] if row[6] else 0,
                "first_player": "Yes"
                if row[7] and "y" in str(row[7]).lower()
                else "No",
                "match_time": row[8] if row[8] else None,
                "winner_deck_url": row[11] if len(row) > 11 else None,
                "loser_deck_url": row[12] if len(row) > 12 else None,
            }

            # Add to wins if avatar won
            if avatar_in_winner:
                total_wins += 1
                wins_matches.append(match_obj.copy())

            # Add to losses if avatar lost
            if avatar_in_loser:
                total_losses += 1
                losses_matches.append(match_obj.copy())
    else:
        # Old schema fallback
        for row in rows:
            deck_json = row[9]

            if not deck_json or deck_json in ("", "{}"):
                continue

            try:
                deck_data = json.loads(deck_json)
                if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                    if deck_data["avatar"][0].get("name") == avatar_name:
                        # In old schema we can't determine if avatar won or lost
                        # Add to both or mark as unknown
                        match_obj = {
                            "match_id": row[11],
                            "winner_id": str(row[0]),
                            "winner_name": generate_pseudonym(row[0]),
                            "loser_id": str(row[2]),
                            "loser_name": generate_pseudonym(row[2]),
                            "date": row[4],
                            "winner_elo_change": row[5] if row[5] else 0,
                            "loser_elo_change": row[6] if row[6] else 0,
                            "first_player": "Yes"
                            if row[7] and "y" in str(row[7]).lower()
                            else "No",
                            "match_time": row[8] if row[8] else None,
                            "winner_deck_url": row[10] if len(row) > 10 else None,
                            "loser_deck_url": None,
                        }
                        # Can't determine wins/losses in old schema, add to general list
                        wins_matches.append(match_obj)
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    total_matches = total_wins + total_losses
    win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0

    return jsonify(
        {
            "name": avatar_name,
            "total_matches": total_matches,
            "wins": total_wins,
            "losses": total_losses,
            "win_rate": round(win_rate, 1),
            "wins_matches": wins_matches[:100],  # Limit to 100 most recent
            "losses_matches": losses_matches[:100],  # Limit to 100 most recent
        }
    )


# Player API endpoint
@app.route("/api/player/<player_id>")
def player_api(player_id):
    import json

    # Get detailed match data from match_records db first
    conn = sqlite3.connect("../discord-bot/match_records.db")
    cur = conn.cursor()

    # Try to get all matches with new columns, fallback to old schema if columns don't exist
    try:
        cur.execute(
            """
            SELECT 
                CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                first_player,
                json_deck_data,
                match_time,
                winner_display_name,
                losser_display_name,
                timestamp,
                winner_elo_change,
                loser_elo_change,
                curiosa_url,
                winner_id,
                losser_id,
                rowid as match_id,
                json_deck_data_winner,
                json_deck_data_loser,
                curiosa_url_winner,
                curiosa_url_loser
            FROM match_records 
            WHERE winner_id = ? OR losser_id = ?
            ORDER BY timestamp DESC
        """,
            (player_id, player_id, player_id),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        # Fallback to old schema without new columns
        cur.execute(
            """
            SELECT 
                CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                first_player,
                json_deck_data,
                match_time,
                winner_display_name,
                losser_display_name,
                timestamp,
                winner_elo_change,
                loser_elo_change,
                curiosa_url,
                winner_id,
                losser_id,
                rowid as match_id
            FROM match_records 
            WHERE winner_id = ? OR losser_id = ?
            ORDER BY timestamp DESC
        """,
            (player_id, player_id, player_id),
        )
        rows = cur.fetchall()

    conn.close()

    if not rows:
        return jsonify({"error": "Player not found"}), 404

    # Get player name from their most recent match
    first_match = rows[0]
    if first_match[0]:  # did_win is True, so player was winner
        player_name = first_match[4]  # winner_display_name
    else:
        player_name = first_match[5]  # losser_display_name

    # Try to get player ELO from elo.db if available
    player_elo = 1500  # Default ELO
    rank = 0
    try:
        elo_conn = sqlite3.connect("../discord-bot/elo.db")
        elo_cur = elo_conn.cursor()
        elo_cur.execute(
            "SELECT elo FROM overall_standings WHERE user_id = ?",
            (player_id,),
        )
        elo_row = elo_cur.fetchone()
        if elo_row:
            player_elo = elo_row[0]
            # Get player rank
            elo_cur.execute(
                "SELECT COUNT(*) FROM overall_standings WHERE elo > ?",
                (player_elo,),
            )
            rank = elo_cur.fetchone()[0] + 1
        elo_conn.close()
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet

    # Calculate detailed stats
    total_matches = len(rows)
    wins = sum(1 for row in rows if row[0])
    losses = total_matches - wins
    win_rate = (wins / total_matches * 100) if total_matches > 0 else 0

    # First player (on the play) stats
    first_player_matches = sum(
        1 for row in rows if row[1] and "y" in str(row[1]).lower()
    )
    first_player_wins = sum(
        1 for row in rows if row[0] and row[1] and "y" in str(row[1]).lower()
    )
    first_player_win_rate = (
        (first_player_wins / first_player_matches * 100)
        if first_player_matches > 0
        else 0
    )

    # On the draw stats
    draw_matches = sum(1 for row in rows if row[1] and "y" not in str(row[1]).lower())
    draw_wins = sum(
        1 for row in rows if row[0] and row[1] and "y" not in str(row[1]).lower()
    )
    draw_win_rate = (draw_wins / draw_matches * 100) if draw_matches > 0 else 0

    # Average match time
    match_times = [
        float(row[3])
        for row in rows
        if row[3] and str(row[3]).replace(".", "").isdigit()
    ]
    avg_match_time = sum(match_times) / len(match_times) if match_times else 0

    # Avatar stats - player's OWN avatars (what they played with)
    avatar_stats = {}
    for row in rows:
        did_win = row[0]
        winner_json = row[13] if len(row) > 13 else None  # json_deck_data_winner
        loser_json = row[14] if len(row) > 14 else None  # json_deck_data_loser

        # Get PLAYER's deck based on match outcome
        # If player won → they are the winner → use winner's deck
        # If player lost → they are the loser → use loser's deck
        deck_json = winner_json if did_win else loser_json

        # Fallback to old json_deck_data column for backward compatibility
        if not deck_json or deck_json == "{}":
            deck_json = row[2]

        if deck_json and deck_json != "{}":
            try:
                deck_data = json.loads(deck_json)
                # Skip if deck_data is empty or has no avatar
                if not deck_data or not deck_data.get("avatar"):
                    continue

                avatar = deck_data.get("avatar", [])
                if not avatar or not avatar[0] or not avatar[0].get("name"):
                    continue

                avatar_name = avatar[0].get("name")

                if avatar_name not in avatar_stats:
                    avatar_stats[avatar_name] = {"wins": 0, "losses": 0}

                if did_win:
                    avatar_stats[avatar_name]["wins"] += 1
                else:
                    avatar_stats[avatar_name]["losses"] += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    # Format avatar stats for response
    avatar_performance = []
    for name, stats in avatar_stats.items():
        total = stats["wins"] + stats["losses"]
        rate = (stats["wins"] / total * 100) if total > 0 else 0
        avatar_performance.append(
            {
                "name": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(rate, 1),
            }
        )
    avatar_performance.sort(key=lambda x: x["wins"] + x["losses"], reverse=True)

    # Avatar matchup records (opponents' avatars)
    opponent_avatar_stats = {}
    for row in rows:
        did_win = row[0]
        winner_json = row[13] if len(row) > 13 else None  # json_deck_data_winner
        loser_json = row[14] if len(row) > 14 else None  # json_deck_data_loser

        # Get OPPONENT's deck based on match outcome
        # If player won → opponent is the loser → use loser's deck
        # If player lost → opponent is the winner → use winner's deck
        opponent_deck_json = loser_json if did_win else winner_json

        # No fallback to old json_deck_data - it only had reporter's deck, not opponent's
        if not opponent_deck_json or opponent_deck_json == "{}":
            continue

        try:
            deck_data = json.loads(opponent_deck_json)
            # Skip if deck_data is empty or has no avatar
            if not deck_data or not deck_data.get("avatar"):
                continue

            avatar = deck_data.get("avatar", [])
            if not avatar or not avatar[0] or not avatar[0].get("name"):
                continue

            opponent_avatar_name = avatar[0].get("name")

            if opponent_avatar_name not in opponent_avatar_stats:
                opponent_avatar_stats[opponent_avatar_name] = {
                    "wins": 0,
                    "losses": 0,
                }

            if did_win:
                opponent_avatar_stats[opponent_avatar_name]["wins"] += 1
            else:
                opponent_avatar_stats[opponent_avatar_name]["losses"] += 1
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            continue

    # Format avatar matchup records for response
    avatar_matchups = []
    for name, stats in opponent_avatar_stats.items():
        total = stats["wins"] + stats["losses"]
        rate = (stats["wins"] / total * 100) if total > 0 else 0
        avatar_matchups.append(
            {
                "opponent_avatar": name,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(rate, 1),
                "total_games": total,
            }
        )
    avatar_matchups.sort(key=lambda x: x["total_games"], reverse=True)

    # Check if logged-in user is the profile owner
    logged_in_user_id = session.get("user_id")
    is_owner = logged_in_user_id is not None and str(logged_in_user_id) == str(
        player_id
    )

    # Auto-set owner to true on localhost for development
    if request.host.startswith("localhost") or request.host.startswith("127.0.0.1"):
        is_owner = True

    # Build match history (last 50 matches)
    match_history = []
    for row in rows[:50]:
        did_win = row[0]
        opponent_name = row[5] if did_win else row[4]
        # When player won, opponent is the loser (losser_id at index 11)
        # When player lost, opponent is the winner (winner_id at index 10)
        opponent_id = str(row[11]) if did_win else str(row[10])
        elo_change = row[7] if did_win else row[8]

        # Get deck URLs from new columns (indices 15, 16) with fallback to old column (index 9)
        # Only include deck URLs for profile owner (privacy)
        player_deck_url = None
        opponent_deck_url = None

        # Get winner/loser deck data
        winner_deck_url = row[15] if len(row) > 15 else None
        loser_deck_url = row[16] if len(row) > 16 else None
        winner_json = row[13] if len(row) > 13 else None
        loser_json = row[14] if len(row) > 14 else None
        old_curiosa_url = row[9]  # Old single URL column
        old_json_deck_data = row[2]  # Old single JSON column

        # Determine player's deck data
        player_deck_url_check = winner_deck_url if did_win else loser_deck_url
        player_deck_json = winner_json if did_win else loser_json

        # Check if player has deck data (URL or JSON) - including fallback to old columns
        has_deck = False
        has_deck_json = False
        if player_deck_url_check and player_deck_url_check not in (
            "No URL provided",
            "Admin reported match",
            "{}",
            "",
            None,
        ):
            has_deck = True
        if player_deck_json and player_deck_json not in ("{}", "", None):
            has_deck = True
            has_deck_json = True
        elif old_curiosa_url and old_curiosa_url not in (
            "No URL provided",
            "Admin reported match",
            "{}",
            "",
            None,
        ):
            # Fallback to old curiosa_url for matches before schema update
            has_deck = True
        if old_json_deck_data and old_json_deck_data not in ("{}", "", None):
            # Fallback to old json_deck_data for matches before schema update
            has_deck = True
            if not has_deck_json:
                has_deck_json = True

        if is_owner:
            # Determine which deck URL belongs to this player
            player_deck_url = winner_deck_url if did_win else loser_deck_url
            opponent_deck_url = loser_deck_url if did_win else winner_deck_url

        match_history.append(
            {
                "match_id": row[12],
                "opponent": opponent_name,
                "opponent_id": opponent_id,
                "result": "Win" if did_win else "Loss",
                "elo_change": elo_change if elo_change else 0,
                "date": row[6],
                "first_player": "Yes"
                if row[1] and "y" in str(row[1]).lower()
                else "No",
                "match_time": row[3] if row[3] else None,
                "replay_url": row[9] if row[9] else None,
                "player_deck_url": player_deck_url,
                "opponent_deck_url": opponent_deck_url,
                "has_deck": has_deck,
                "has_deck_json": has_deck_json,
            }
        )

    # Extract recent unique decks (only for profile owner)
    recent_decks = []
    if is_owner:
        seen_urls = set()
        for row in rows:
            did_win = row[0]
            winner_deck_url = row[15] if len(row) > 15 else row[9]
            loser_deck_url = row[16] if len(row) > 16 else None
            winner_json = row[13] if len(row) > 13 else row[2]
            loser_json = row[14] if len(row) > 14 else None

            # Get this player's deck URL and JSON
            player_deck_url = winner_deck_url if did_win else loser_deck_url
            player_deck_json = winner_json if did_win else loser_json

            # Skip if no URL or invalid URL
            if not player_deck_url or player_deck_url in (
                "No URL provided",
                "Admin reported match",
                "{}",
            ):
                continue

            # Skip if we've already seen this URL
            if player_deck_url in seen_urls:
                continue

            seen_urls.add(player_deck_url)

            # Try to extract avatar and deck name from JSON
            avatar_name = "Unknown"
            deck_name = "Unnamed Deck"
            if player_deck_json and player_deck_json not in ("", "{}"):
                try:
                    deck_data = json.loads(player_deck_json)
                    if deck_data.get("avatar") and len(deck_data["avatar"]) > 0:
                        avatar_name = deck_data["avatar"][0].get("name", "Unknown")
                    if deck_data.get("name"):
                        deck_name = deck_data["name"]
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            recent_decks.append(
                {
                    "url": player_deck_url,
                    "avatar": avatar_name,
                    "deck_name": deck_name,
                    "date": row[6],
                }
            )

            if len(recent_decks) >= 10:
                break

    return jsonify(
        {
            "id": player_id,
            "name": player_name,
            "elo": player_elo,
            "rank": rank,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "on_play_wins": first_player_wins,
            "on_play_matches": first_player_matches,
            "on_play_win_rate": round(first_player_win_rate, 1),
            "on_draw_wins": draw_wins,
            "on_draw_matches": draw_matches,
            "on_draw_win_rate": round(draw_win_rate, 1),
            "avg_match_time": round(avg_match_time, 1),
            # Privacy: Only show avatar stats to profile owner
            "avatar_performance": avatar_performance if is_owner else [],
            "avatar_matchups": avatar_matchups if is_owner else [],
            "recent_decks": recent_decks if is_owner else [],
            "matches": match_history,
            "is_owner": is_owner,
        }
    )


@app.route("/api/avatars")
def avatars_api():
    """API endpoint for global avatar stats from all matches with deck data"""
    import json

    try:
        conn = sqlite3.connect("../discord-bot/match_records.db")
        cur = conn.cursor()

        # Try to get all matches with separated winner/loser deck data
        try:
            cur.execute(
                """
                SELECT 
                    json_deck_data_winner,
                    json_deck_data_loser
                FROM match_records 
                WHERE (json_deck_data_winner IS NOT NULL AND json_deck_data_winner != '' AND json_deck_data_winner != '{}') 
                   OR (json_deck_data_loser IS NOT NULL AND json_deck_data_loser != '' AND json_deck_data_loser != '{}')
            """
            )
            rows = cur.fetchall()
            use_new_columns = True
        except sqlite3.OperationalError:
            # Fallback to old json_deck_data column
            cur.execute(
                """
                SELECT 
                    CASE WHEN reporter_id = winner_id THEN 1 ELSE 0 END as reporter_won,
                    json_deck_data
                FROM match_records 
                WHERE json_deck_data IS NOT NULL AND json_deck_data != '' AND json_deck_data != '{}'
            """
            )
            rows = cur.fetchall()
            use_new_columns = False
        conn.close()
    except sqlite3.OperationalError:
        # Table doesn't exist or database not found
        return jsonify([])

    # Calculate avatar stats across all matches
    avatar_stats = {}

    if use_new_columns:
        for row in rows:
            winner_deck_data_str = row[0]
            loser_deck_data_str = row[1]

            # Process winner's deck
            if winner_deck_data_str and winner_deck_data_str not in ("", "{}"):
                try:
                    deck_data = json.loads(winner_deck_data_str)
                    avatar = deck_data.get("avatar", [{}])
                    avatar_name = (
                        avatar[0].get("name", "Unknown") if avatar else "Unknown"
                    )

                    if avatar_name and avatar_name != "Unknown":
                        if avatar_name not in avatar_stats:
                            avatar_stats[avatar_name] = {"wins": 0, "losses": 0}
                        avatar_stats[avatar_name]["wins"] += 1
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass

            # Process loser's deck
            if loser_deck_data_str and loser_deck_data_str not in ("", "{}"):
                try:
                    deck_data = json.loads(loser_deck_data_str)
                    avatar = deck_data.get("avatar", [{}])
                    avatar_name = (
                        avatar[0].get("name", "Unknown") if avatar else "Unknown"
                    )

                    if avatar_name and avatar_name != "Unknown":
                        if avatar_name not in avatar_stats:
                            avatar_stats[avatar_name] = {"wins": 0, "losses": 0}
                        avatar_stats[avatar_name]["losses"] += 1
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass
    else:
        # Old logic for backward compatibility
        for row in rows:
            reporter_won = row[0]
            deck_data_str = row[1]

            if not deck_data_str:
                continue

            try:
                deck_data = json.loads(deck_data_str)
                avatar = deck_data.get("avatar", [{}])
                avatar_name = avatar[0].get("name", "Unknown") if avatar else "Unknown"

                if avatar_name == "Unknown" or not avatar_name:
                    continue

                if avatar_name not in avatar_stats:
                    avatar_stats[avatar_name] = {"wins": 0, "losses": 0}

                if reporter_won:
                    avatar_stats[avatar_name]["wins"] += 1
                else:
                    avatar_stats[avatar_name]["losses"] += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

    # Format for response and sort by total games played
    avatar_list = []
    for name, stats in avatar_stats.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            win_rate = stats["wins"] / total * 100
            avatar_list.append(
                {
                    "name": name,
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "total": total,
                    "win_rate": round(win_rate, 1),
                }
            )

    # Sort by total games played (most popular first)
    avatar_list.sort(key=lambda x: x["total"], reverse=True)

    return jsonify(avatar_list)


@app.route("/api/rules-assistant", methods=["POST"])
def rules_assistant_api():
    """API endpoint for Rules Assistant chat"""
    try:
        data = request.get_json()
        question = data.get("question", "").strip()

        if not question:
            return jsonify({"success": False, "error": "Question is required"}), 400

        if len(question) > 500:
            return jsonify(
                {"success": False, "error": "Question is too long (max 500 characters)"}
            ), 400

        # Get rules assistant components
        retriever, generator = get_rules_assistant()

        # Retrieve relevant context
        retrieved_chunks = retriever.search(question, top_k=5)

        # Generate answer
        response = generator.generate(question, retrieved_chunks)

        return jsonify(
            {"success": True, "answer": response.answer, "sources": response.sources}
        )

    except Exception as e:
        logger.error(f"Rules Assistant API error: {e}", exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "Failed to process your question. Please try again.",
            }
        ), 500


@app.route("/avatar-images/<path:filename>")
def avatar_images(filename):
    """Serve avatar images from templates/avatar_imgs folder"""
    from flask import send_from_directory

    avatar_imgs_dir = os.path.join(app.root_path, "templates", "avatar_imgs")
    return send_from_directory(avatar_imgs_dir, filename)


if __name__ == "__main__":
    # This block is for LOCAL DEVELOPMENT ONLY
    # Production deployment uses gunicorn with gunicorn_config.py
    # See DEPLOYMENT.md for production setup instructions
    app.run(debug=True, host="0.0.0.0", port=5000)
