"""Player API routes."""

import json
import logging
import os
import sqlite3

from flask import Blueprint, jsonify, session, request

import re

from webapp_config import MATCH_RECORDS_DB_PATH, ELO_DB_PATH, VALID_API_KEYS, SEASON_FILTERS, CARD_IMAGES_DIR
from services.match import MatchService
from repositories.user_profiles import UserProfileRepository
from utils.auth import is_admin

logger = logging.getLogger(__name__)

players_bp = Blueprint("players", __name__)

# ---------------------------------------------------------------------------
# Card image lookup (module-level cache)
# ---------------------------------------------------------------------------

_card_image_map: dict[str, str] | None = None


def _get_card_image_map() -> dict[str, str]:
    global _card_image_map
    if _card_image_map is not None:
        return _card_image_map
    mapping: dict[str, str] = {}
    if CARD_IMAGES_DIR.exists():
        all_files = sorted(os.listdir(CARD_IMAGES_DIR))
        png_files = [f for f in all_files if f.lower().endswith((".png", ".jpg", ".jpeg"))]
        webp_files = [f for f in all_files if f.lower().endswith(".webp")]
        for fname in png_files + webp_files:
            base = re.sub(r"\.(png|jpg|jpeg|webp)$", "", fname, flags=re.IGNORECASE)
            parts = base.split("-")
            if len(parts) >= 2:
                name_key = parts[1]
                mapping[name_key] = fname
    _card_image_map = mapping
    return mapping


def _resolve_card_image(card_name: str) -> str | None:
    mapping = _get_card_image_map()
    key = card_name.lower().replace(" ", "_").replace("'", "").replace(",", "")
    return mapping.get(key)


# ---------------------------------------------------------------------------
# Tournament seed cache for similar-deck lookups
# ---------------------------------------------------------------------------

_seed_decks: list | None = None


def _get_seed_decks() -> list:
    """Return cached list of tournament/admin seed DeckRecord objects."""
    global _seed_decks
    if _seed_decks is not None:
        return _seed_decks
    try:
        from repositories.deck_rec_repo import DeckRecRepository
        _seed_decks = DeckRecRepository().load_seed_decks()
    except Exception as e:
        logger.warning("Could not load seed decks for similarity: %s", e)
        _seed_decks = []
    return _seed_decks


def _find_similar_seeds(deck: dict, top_n: int = 5) -> list[dict]:
    """Return the top_n most similar tournament seed decks for a given player deck.

    Uses Jaccard similarity on card name sets across spellbook + atlas sections.
    """
    from services.deck_similarity import jaccard

    # Build card name set from the player's deck
    player_cards: set[str] = set()
    for section in ("spellbook", "atlas"):
        for card in deck.get(section, []) or []:
            if card and card.get("name"):
                player_cards.add(card["name"].strip().lower())

    if not player_cards:
        return []

    player_set = frozenset(player_cards)
    image_map = _get_card_image_map()

    scored = []
    for seed in _get_seed_decks():
        score = jaccard(player_set, seed.card_names)
        if score > 0:
            scored.append((score, seed))

    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    for score, seed in scored[:top_n]:
        # Resolve avatar image
        avatar_img = None
        if seed.avatar_name:
            avatar_key = seed.avatar_name.lower().replace(" ", "_").replace("'", "").replace(",", "")
            avatar_img = image_map.get(avatar_key)

        result.append({
            "deck_id": seed.deck_id,
            "deck_name": seed.deck_name,
            "avatar_name": seed.avatar_name,
            "player_name": seed.player_name,
            "event_name": seed.event_name,
            "curiosa_url": seed.curiosa_url,
            "similarity": round(score, 3),
            "avatar_image": avatar_img,
        })

    return result


def _extract_deck_info(deck_json):
    """Extract avatar name and element list from a deck JSON string."""
    avatar_name = None
    elements = []
    if not deck_json or deck_json in ("{}", ""):
        return avatar_name, elements
    try:
        deck_data = json.loads(deck_json)
        avatar_list = deck_data.get("avatar", [])
        if avatar_list:
            for av in avatar_list:
                if av and av.get("type") == "Avatar" and av.get("name"):
                    avatar_name = av.get("name")
                    break
            if not avatar_name and avatar_list[0] and avatar_list[0].get("name"):
                avatar_name = avatar_list[0].get("name")
        elements_set = set()
        for section in ["spellbook", "sideboard"]:
            for card in deck_data.get(section, []) or []:
                card_elements = card.get("elements", "")
                if card_elements and card_elements != "None":
                    for el in card_elements.split(","):
                        el = el.strip()
                        if el in ("Earth", "Fire", "Water", "Air"):
                            elements_set.add(el)
        elements = sorted(elements_set)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
        pass
    return avatar_name, elements


@players_bp.route("/deck-snapshot/<int:match_id>/<player_id>")
def deck_snapshot(match_id, player_id):
    """Get deck snapshot for a specific player in a match."""
    # Normalize player_id (strip 'google_' prefix for Google OAuth users)
    player_id_str = str(player_id)
    if player_id_str.startswith("google_"):
        player_id = player_id_str[7:]  # Remove 'google_' prefix

    # Normalize logged_in_user_id for comparison
    logged_in_user_id = session.get("user_id")
    if logged_in_user_id is not None:
        logged_in_id_str = str(logged_in_user_id)
        if logged_in_id_str.startswith("google_"):
            logged_in_id_str = logged_in_id_str[7:]  # Remove 'google_' prefix
        is_owner = str(logged_in_id_str) == str(player_id)
    else:
        is_owner = False

    # API key grants access (for server-to-server calls)
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in VALID_API_KEYS:
        is_owner = True

    # Admins have full access
    if is_admin():
        is_owner = True

    if not is_owner:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        service = MatchService()
        result = service.get_deck_snapshot(match_id, player_id)

        if result is None:
            return jsonify({"error": "Match not found"}), 404

        if "error" in result:
            if "not found" in result["error"].lower():
                return jsonify(result), 404
            return jsonify(result), 400

        # Inject image filenames into card data
        deck = result.get("deck", {})
        for section in ("spellbook", "atlas", "sideboard", "avatar"):
            for card in deck.get(section, []) or []:
                if card and card.get("name"):
                    card["image"] = _resolve_card_image(card["name"])

        # Find similar tournament decks
        result["similar_decks"] = _find_similar_seeds(deck)

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching deck snapshot: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@players_bp.route("/players/<player_id>/deck-stats")
def get_deck_stats(player_id):
    """Get detailed stats for a specific deck URL for a player."""
    deck_url = request.args.get("url", "").strip()
    if not deck_url:
        return jsonify({"error": "url parameter required"}), 400

    # Normalize player_id
    player_id_str = str(player_id)
    if player_id_str.startswith("google_"):
        player_id = player_id_str[7:]

    # Auth: owner or admin only
    logged_in_user_id = session.get("user_id")
    is_owner = False
    if logged_in_user_id is not None:
        logged_in_id_str = str(logged_in_user_id)
        if logged_in_id_str.startswith("google_"):
            logged_in_id_str = logged_in_id_str[7:]
        is_owner = logged_in_id_str == str(player_id)
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in VALID_API_KEYS:
        is_owner = True
    if is_admin():
        is_owner = True
    if not is_owner:
        return jsonify({"error": "Unauthorized"}), 403

    # Normalise the target URL the same way the player page does
    deck_url = deck_url.split("?")[0]

    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Pull every match for this player from both active and archive tables
    all_rows = []
    for table, id_col in [("match_records", "rowid"), ("match_records_archive", "rowid + 1000000000")]:
        try:
            cur.execute(
                f"""
                SELECT
                    CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                    winner_display_name,
                    losser_display_name,
                    winner_id,
                    losser_id,
                    timestamp,
                    winner_elo_change,
                    loser_elo_change,
                    match_time,
                    {id_col} as match_id,
                    COALESCE(curiosa_url_winner, curiosa_url) as winner_deck_url,
                    curiosa_url_loser as loser_deck_url,
                    json_deck_data_winner as winner_json,
                    json_deck_data_loser as loser_json,
                    winner_went_first,
                    loser_went_first
                FROM {table}
                WHERE winner_id = ? OR losser_id = ?
                ORDER BY timestamp DESC
                """,
                (player_id, player_id, player_id),
            )
            all_rows.extend(cur.fetchall())
        except sqlite3.OperationalError:
            try:
                cur.execute(
                    f"""
                    SELECT
                        CASE WHEN winner_id = ? THEN 1 ELSE 0 END as did_win,
                        winner_display_name,
                        losser_display_name,
                        winner_id,
                        losser_id,
                        timestamp,
                        winner_elo_change,
                        loser_elo_change,
                        match_time,
                        {id_col} as match_id,
                        COALESCE(curiosa_url_winner, curiosa_url) as winner_deck_url,
                        NULL as loser_deck_url,
                        json_deck_data as winner_json,
                        NULL as loser_json,
                        NULL as winner_went_first,
                        NULL as loser_went_first
                    FROM {table}
                    WHERE winner_id = ? OR losser_id = ?
                    ORDER BY timestamp DESC
                    """,
                    (player_id, player_id, player_id),
                )
                all_rows.extend(cur.fetchall())
            except sqlite3.OperationalError:
                pass
    conn.close()

    wins = 0
    losses = 0
    deck_name = "Unnamed Deck"
    avatar = "Unknown"
    vs_avatars = {}   # opponent_avatar -> {wins, losses}
    on_play = {"wins": 0, "losses": 0}
    on_draw = {"wins": 0, "losses": 0}
    match_history = []
    stored_deck_json = None

    for row in all_rows:
        did_win = row["did_win"]
        player_url = row["winner_deck_url"] if did_win else row["loser_deck_url"]
        if not player_url:
            continue
        # Normalise URL
        player_url = player_url.split("?")[0]
        if player_url != deck_url:
            continue

        player_json = row["winner_json"] if did_win else row["loser_json"]
        opp_json = row["loser_json"] if did_win else row["winner_json"]
        opp_name = row["losser_display_name"] if did_win else row["winner_display_name"]
        opp_id = str(row["losser_id"]) if did_win else str(row["winner_id"])
        elo_change = row["winner_elo_change"] if did_win else row["loser_elo_change"]

        # Extract own deck info (use first match that has it)
        if avatar == "Unknown" and player_json and player_json not in ("{}", ""):
            av, _ = _extract_deck_info(player_json)
            if av:
                avatar = av
            try:
                d = json.loads(player_json)
                if d.get("name"):
                    deck_name = d["name"]
            except (json.JSONDecodeError, TypeError):
                pass

        # Store deck JSON for card display
        if stored_deck_json is None and player_json and player_json not in ("{}", ""):
            stored_deck_json = player_json

        opp_avatar, _ = _extract_deck_info(opp_json)
        opp_avatar = opp_avatar or "Unknown"

        if opp_avatar not in vs_avatars:
            vs_avatars[opp_avatar] = {"wins": 0, "losses": 0}
        if did_win:
            wins += 1
            vs_avatars[opp_avatar]["wins"] += 1
        else:
            losses += 1
            vs_avatars[opp_avatar]["losses"] += 1

        # On play / on draw
        went_first_val = row["winner_went_first"] if did_win else row["loser_went_first"]
        if went_first_val is not None:
            on_play_flag = "y" in str(went_first_val).lower()
            bucket = on_play if on_play_flag else on_draw
            if did_win:
                bucket["wins"] += 1
            else:
                bucket["losses"] += 1

        match_history.append({
            "match_id": row["match_id"],
            "date": row["timestamp"],
            "result": "Win" if did_win else "Loss",
            "opponent": opp_name,
            "opponent_id": opp_id,
            "opponent_avatar": opp_avatar,
            "elo_change": elo_change,
            "match_time": row["match_time"],
        })

    total = wins + losses
    win_rate = round(wins / total * 100, 1) if total > 0 else 0

    matchups = []
    for opp_av, rec in sorted(vs_avatars.items(), key=lambda x: x[1]["wins"] + x[1]["losses"], reverse=True):
        t = rec["wins"] + rec["losses"]
        matchups.append({
            "opponent_avatar": opp_av,
            "wins": rec["wins"],
            "losses": rec["losses"],
            "total": t,
            "win_rate": round(rec["wins"] / t * 100, 1) if t > 0 else 0,
        })

    def _play_stats(bucket):
        t = bucket["wins"] + bucket["losses"]
        return {"wins": bucket["wins"], "losses": bucket["losses"], "total": t,
                "win_rate": round(bucket["wins"] / t * 100, 1) if t > 0 else 0}

    # Build deck card data with resolved images
    deck_data_response = {}
    if stored_deck_json:
        try:
            deck_data = json.loads(stored_deck_json)
            for section in ("spellbook", "atlas", "sideboard", "avatar"):
                for card in deck_data.get(section, []) or []:
                    if card and card.get("name"):
                        card["image"] = _resolve_card_image(card["name"])
            deck_data_response = deck_data
        except Exception:
            pass

    return jsonify({
        "deck_name": deck_name,
        "avatar": avatar,
        "url": deck_url,
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_rate": win_rate,
        "matchups": matchups,
        "on_play": _play_stats(on_play),
        "on_draw": _play_stats(on_draw),
        "matches": match_history,
        "deck": deck_data_response,
    })


def _get_limited_stats(player_id: str) -> dict:
    """Fetch limited arena stats for a player from match_records.db and elo.db."""
    result = {
        "has_data": False,
        "elo": 1500,
        "arena_runs": [],
        "recent_matches": [],
        "total_wins": 0,
        "total_losses": 0,
        "total_matches": 0,
        "win_rate": 0,
    }

    # Limited ELO from elo.db
    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()
        elo_cur.execute("SELECT elo FROM limited_elo WHERE user_id = ?", (player_id,))
        row = elo_cur.fetchone()
        if row:
            result["elo"] = row[0]
            result["has_data"] = True
        elo_conn.close()
    except sqlite3.OperationalError:
        pass

    # Arena runs + matches from match_records.db
    try:
        conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
        cur = conn.cursor()

        # Arena runs
        cur.execute(
            """SELECT run_id, wins, losses, deck_url, status, starting_elo, created_at, completed_at
               FROM limited_arena_runs WHERE user_id = ? ORDER BY created_at DESC""",
            (player_id,),
        )
        runs = cur.fetchall()
        if runs:
            result["has_data"] = True
            result["arena_runs"] = [
                {
                    "run_id": r[0], "wins": r[1], "losses": r[2], "deck_url": r[3],
                    "status": r[4], "starting_elo": r[5],
                    "created_at": r[6][:10] if r[6] else None,
                    "completed_at": r[7][:10] if r[7] else None,
                }
                for r in runs
            ]

        # Recent limited matches
        cur.execute(
            """SELECT match_id, winner_id, winner_display_name, loser_id, loser_display_name,
                      timestamp, winner_elo_change, loser_elo_change, match_time
               FROM limited_match_records
               WHERE winner_id = ? OR loser_id = ?
               ORDER BY timestamp DESC LIMIT 20""",
            (player_id, player_id),
        )
        matches = cur.fetchall()
        if matches:
            result["has_data"] = True
            total_wins = sum(1 for m in matches if str(m[1]) == str(player_id))
            total_losses = sum(1 for m in matches if str(m[3]) == str(player_id))
            total = total_wins + total_losses
            result["total_wins"] = total_wins
            result["total_losses"] = total_losses
            result["total_matches"] = total
            result["win_rate"] = round(total_wins / total * 100, 1) if total > 0 else 0
            result["recent_matches"] = [
                {
                    "match_id": m[0],
                    "winner_id": str(m[1]),
                    "winner_name": m[2] or "Unknown",
                    "loser_id": str(m[3]),
                    "loser_name": m[4] or "Unknown",
                    "timestamp": m[5],
                    "winner_elo_change": m[6] or 0,
                    "loser_elo_change": m[7] or 0,
                    "match_time": m[8] or 0,
                }
                for m in matches
            ]

        conn.close()
    except sqlite3.OperationalError:
        pass

    return result


@players_bp.route("/players/search")
def search_players():
    """Public player search for autocomplete. GET /api/players/search?q=<query>&limit=8"""
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify({"players": []})
    limit = min(request.args.get("limit", 8, type=int), 20)
    try:
        repo = UserProfileRepository()
        results = repo.search_users(query, limit=limit)
        players = [
            {"user_id": r["user_id"], "display_name": r["display_name"], "avatar": r.get("avatar"), "provider": r.get("provider", "discord")}
            for r in results
        ]
        return jsonify({"players": players})
    except Exception as e:
        logger.error(f"Player search error: {e}")
        return jsonify({"players": []})


@players_bp.route("/player/<player_id>")
def player_api(player_id):
    """Get comprehensive player stats and match history.

    Query parameters:
    - event: Filter by event. Values: 'lifetime' (default), 'current', or event_id (int)
    - source: ELO source filter. Values: 'web', 'bot', or 'auto' (default)
    """
    # Store original player_id (with google_ prefix if present)
    original_player_id = str(player_id)

    # Get source parameter (web, bot, or auto)
    # Default to "bot" for now since all matches are in match_records table
    source = request.args.get("source", "bot")

    # Validate source parameter
    if source not in ("web", "bot"):
        return jsonify({"error": "Invalid source parameter. Must be 'web' or 'bot'"}), 400

    # Normalize player_id for INTEGER-based tables (match_records, overall_standings)
    # Strip 'google_' prefix for these legacy tables
    player_id_normalized = original_player_id
    if original_player_id.startswith("google_"):
        player_id_normalized = original_player_id[7:]  # Remove 'google_' prefix

    # Keep player_id as string to avoid overflow with large Google OAuth IDs
    # SQLite's type affinity will handle string-to-integer comparison automatically
    # Validate that it's numeric (but don't convert to int)
    try:
        int(player_id_normalized)  # Validate numeric format
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid player ID"}), 400

    event_filter = request.args.get("event", "lifetime")

    conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
    cur = conn.cursor()

    # Count matches and find most recent match in both tables to determine available sources
    has_web_matches = False
    has_bot_matches = False
    most_recent_web = None
    most_recent_bot = None

    # Check for web matches (match_reports_web table with TEXT IDs)
    try:
        cur.execute(
            """
            SELECT COUNT(*), MAX(timestamp) FROM match_reports_web
            WHERE winner_id = ? OR losser_id = ?
            """,
            (original_player_id, original_player_id),
        )
        row = cur.fetchone()
        web_count = row[0]
        most_recent_web = row[1]
        has_web_matches = web_count > 0
    except sqlite3.OperationalError:
        # Table may not exist yet
        pass

    # Check for bot matches (match_records table with INTEGER IDs)
    try:
        cur.execute(
            """
            SELECT COUNT(*), MAX(timestamp) FROM match_records
            WHERE winner_id = ? OR losser_id = ?
            """,
            (player_id_normalized, player_id_normalized),
        )
        row = cur.fetchone()
        bot_count = row[0]
        most_recent_bot = row[1]

        # Also check archive table (matches moved there by !end_event)
        try:
            cur.execute(
                """
                SELECT COUNT(*), MAX(timestamp) FROM match_records_archive
                WHERE winner_id = ? OR losser_id = ?
                """,
                (player_id_normalized, player_id_normalized),
            )
            archive_row = cur.fetchone()
            bot_count += archive_row[0] if archive_row else 0
            # Use the most recent timestamp from either table
            if archive_row and archive_row[1]:
                if not most_recent_bot or archive_row[1] > most_recent_bot:
                    most_recent_bot = archive_row[1]
        except sqlite3.OperationalError:
            # Archive table may not exist yet
            pass

        has_bot_matches = bot_count > 0
    except sqlite3.OperationalError:
        pass

    # Fallback: if requested source has no matches, switch to the other
    if source == "bot" and not has_bot_matches and has_web_matches:
        source = "web"
    elif source == "web" and not has_web_matches and has_bot_matches:
        source = "bot"

    # Determine which tables to query based on event filter and source
    include_current_matches = True  # From match_records or match_reports_web table
    include_archived_matches = True  # From match_records_archive table
    archive_event_id = None  # Specific event to filter in archive

    # Event date range for filtering web matches (which have no event_id column)
    event_start_date = None
    event_end_date = None

    if event_filter == "current":
        # Only current event matches (from match_records or match_reports_web table)
        include_archived_matches = False
        # Look up active event start_date for web match filtering
        try:
            elo_conn_tmp = sqlite3.connect(str(ELO_DB_PATH))
            elo_cur_tmp = elo_conn_tmp.cursor()
            elo_cur_tmp.execute(
                "SELECT start_date FROM events WHERE is_active = 1 LIMIT 1"
            )
            ev_row = elo_cur_tmp.fetchone()
            if ev_row:
                event_start_date = ev_row[0]
            elo_conn_tmp.close()
        except sqlite3.OperationalError:
            pass
    elif event_filter != "lifetime":
        if isinstance(event_filter, str) and event_filter.startswith("season_"):
            # Season date-range filter - query both tables by timestamp
            for sf in SEASON_FILTERS:
                if sf["id"] == event_filter:
                    event_start_date = sf["start_date"]
                    event_end_date = sf["end_date"]
                    break
            # For season filters, include both current and archived matches
            # (filter by timestamp, not event_id)
            include_current_matches = True
            include_archived_matches = True
        else:
            # Specific past event - only from archive with that event_id
            try:
                archive_event_id = int(event_filter)
                include_current_matches = False
                # Look up past event date range for web match filtering
                elo_conn_tmp = sqlite3.connect(str(ELO_DB_PATH))
                elo_cur_tmp = elo_conn_tmp.cursor()
                elo_cur_tmp.execute(
                    "SELECT start_date, end_date FROM events WHERE event_id = ?",
                    (archive_event_id,),
                )
                ev_row = elo_cur_tmp.fetchone()
                if ev_row:
                    event_start_date = ev_row[0]
                    event_end_date = ev_row[1]
                elo_conn_tmp.close()
            except (ValueError, TypeError):
                pass  # Invalid event_id, fall back to lifetime
            except sqlite3.OperationalError:
                pass

    rows = []
    is_season_filter = isinstance(event_filter, str) and event_filter.startswith("season_")

    # Choose player ID and table based on source
    if source == "web":
        # Use original_player_id (with google_ prefix) for TEXT-based match_reports_web table
        query_player_id = original_player_id
    else:  # bot
        # Use normalized player_id (without google_ prefix) for INTEGER-based match_records table
        query_player_id = player_id_normalized

    # Query current matches if needed
    # For web source: also query when viewing a past event (filter by date range)
    web_should_query = (source == "web") and (
        include_current_matches or archive_event_id is not None
    )
    if web_should_query:
        # Query match_reports_web table (web-based matches)
        # Build date filter for event scoping
        date_filter = ""
        date_params = (query_player_id, query_player_id, query_player_id)
        if event_start_date:
            date_filter += " AND timestamp >= ?"
            date_params += (event_start_date,)
        if event_end_date:
            date_filter += " AND timestamp <= ?"
            date_params += (event_end_date,)
        try:
            cur.execute(
                f"""
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
                    match_id,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    winner_went_first,
                    loser_went_first,
                    match_type
                FROM match_reports_web
                WHERE (winner_id = ? OR losser_id = ?){date_filter}
                ORDER BY timestamp DESC
            """,
                date_params,
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Table may not exist yet
            rows = []
    elif include_current_matches:
        # Query match_records table (bot-based matches)
        # Build season date filter for bot matches
        bot_date_filter = ""
        bot_base_params = (query_player_id, query_player_id, query_player_id)
        if is_season_filter and event_start_date and event_end_date:
            bot_date_filter = " AND timestamp >= ? AND timestamp <= ?"
            bot_base_params = (query_player_id, query_player_id, query_player_id, event_start_date, event_end_date)
        # Try new schema first, fallback to old
        try:
            cur.execute(
                f"""
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
                    curiosa_url_loser,
                    winner_went_first,
                    loser_went_first,
                    match_type
                FROM match_records
                WHERE (winner_id = ? OR losser_id = ?){bot_date_filter}
                ORDER BY timestamp DESC
            """,
                bot_base_params,
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Fallback: try without new columns but with deck columns
            try:
                cur.execute(
                    f"""
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
                        curiosa_url_loser,
                        NULL as winner_went_first,
                        NULL as loser_went_first,
                        NULL as match_type
                    FROM match_records
                    WHERE (winner_id = ? OR losser_id = ?){bot_date_filter}
                    ORDER BY timestamp DESC
                """,
                    bot_base_params,
                )
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                # Final fallback: minimal columns for very old schema or missing table
                try:
                    cur.execute(
                        f"""
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
                            NULL as json_deck_data_winner,
                            NULL as json_deck_data_loser,
                            NULL as curiosa_url_winner,
                            NULL as curiosa_url_loser,
                            NULL as winner_went_first,
                            NULL as loser_went_first,
                            NULL as match_type
                        FROM match_records
                        WHERE (winner_id = ? OR losser_id = ?){bot_date_filter}
                        ORDER BY timestamp DESC
                    """,
                        bot_base_params,
                    )
                    rows = cur.fetchall()
                except sqlite3.OperationalError:
                    # Table doesn't exist at all - no bot matches available
                    rows = []

    # Also check archive table for historical matches (if needed based on filter)
    # Note: Archive is only available for bot matches (match_records_archive)
    archived_rows = []
    if include_archived_matches and source == "bot":
        # Build the WHERE clause based on event filter
        if archive_event_id is not None:
            event_filter_clause = " AND event_id = ?"
            query_params = (query_player_id, query_player_id, query_player_id, archive_event_id)
        elif is_season_filter and event_start_date and event_end_date:
            event_filter_clause = " AND timestamp >= ? AND timestamp <= ?"
            query_params = (query_player_id, query_player_id, query_player_id, event_start_date, event_end_date)
        else:
            event_filter_clause = ""
            query_params = (query_player_id, query_player_id, query_player_id)

        try:
            cur.execute(
                f"""
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
                    rowid + 1000000000 as match_id,
                    json_deck_data_winner,
                    json_deck_data_loser,
                    curiosa_url_winner,
                    curiosa_url_loser,
                    winner_went_first,
                    loser_went_first,
                    NULL as match_type
                FROM match_records_archive
                WHERE (winner_id = ? OR losser_id = ?){event_filter_clause}
                ORDER BY timestamp DESC
            """,
                query_params,
            )
            archived_rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Try without new columns
            try:
                cur.execute(
                    f"""
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
                        rowid + 1000000000 as match_id,
                        json_deck_data_winner,
                        json_deck_data_loser,
                        curiosa_url_winner,
                        curiosa_url_loser,
                        NULL as winner_went_first,
                        NULL as loser_went_first,
                        NULL as match_type
                    FROM match_records_archive
                    WHERE (winner_id = ? OR losser_id = ?){event_filter_clause}
                    ORDER BY timestamp DESC
                """,
                    query_params,
                )
                archived_rows = cur.fetchall()
            except sqlite3.OperationalError:
                pass  # Archive table may not exist

    conn.close()

    # Combine current and archived matches
    rows = list(rows) + list(archived_rows)

    # Get solo match reports (bot-only)
    solo_rows = []
    if source == "bot":
        try:
            solo_conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
            solo_cur = solo_conn.cursor()

            query = """
                SELECT
                    is_winner,
                    first_player,
                    json_deck_data,
                    match_time,
                    CASE WHEN is_winner THEN reporter_name ELSE opponent_name END,
                    CASE WHEN is_winner THEN opponent_name ELSE reporter_name END,
                    report_date,
                    0,
                    0,
                    curiosa_link,
                    CASE WHEN is_winner THEN reporter_id ELSE 0 END,
                    CASE WHEN is_winner THEN 0 ELSE reporter_id END,
                    rowid,
                    CASE WHEN is_winner THEN json_deck_data ELSE NULL END,
                    CASE WHEN is_winner THEN NULL ELSE json_deck_data END,
                    CASE WHEN is_winner THEN curiosa_link ELSE NULL END,
                    CASE WHEN is_winner THEN NULL ELSE curiosa_link END,
                    NULL as winner_went_first,
                    NULL as loser_went_first
                FROM solo_match_reports
                WHERE reporter_id = ?
                ORDER BY report_date DESC
            """
            solo_cur.execute(query, (query_player_id,))
            solo_rows = solo_cur.fetchall()

            solo_conn.close()
        except Exception as e:
            logger.warning(f"Could not fetch solo_match_reports: {e}")

    all_rows = rows + solo_rows

    # Get player ELO and name from ELO database first
    player_elo = 1500
    event_elo = 1500
    rank = 0
    player_name_from_elo = None
    displayed_elo = 1500  # The ELO to display based on filter
    displayed_rank = 0
    paper_elo = 1500  # Always fetch both for toggle
    online_elo = 1500
    paper_event_elo = 1500
    online_event_elo = 1500

    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()

        # Choose ELO columns based on source
        if source == "web":
            # Query paper ELO from paper_standings table (source of truth for web matches)
            # paper_standings uses TEXT primary key to support google_ prefixed IDs
            try:
                elo_cur.execute(
                    "SELECT paper_elo, user_display_name, paper_event_elo FROM paper_standings WHERE user_id = ?",
                    (original_player_id,),
                )
                paper_row = elo_cur.fetchone()
                if paper_row:
                    player_elo = paper_row[0] if paper_row[0] else 1500
                    player_name_from_elo = paper_row[1]
                    event_elo = paper_row[2] if paper_row[2] else 1500
                    paper_elo = player_elo
                    paper_event_elo = event_elo
                    # Calculate rank based on paper_elo among all paper players
                    elo_cur.execute(
                        "SELECT COUNT(*) FROM paper_standings WHERE paper_elo > ?", (player_elo,)
                    )
                    rank = elo_cur.fetchone()[0] + 1
            except sqlite3.OperationalError:
                pass  # paper_standings table may not exist yet

            # Also get online ELO from overall_standings for the toggle
            try:
                elo_cur.execute(
                    "SELECT online_elo, user_display_name, online_event_elo FROM overall_standings WHERE user_id = ?",
                    (player_id_normalized,),
                )
                online_row = elo_cur.fetchone()
                if online_row:
                    online_elo = online_row[0] if online_row[0] else 1500
                    online_event_elo = online_row[2] if len(online_row) > 2 and online_row[2] else 1500
                    if not player_name_from_elo:
                        player_name_from_elo = online_row[1]
            except sqlite3.OperationalError:
                pass
        else:  # bot
            # Query online ELO columns (bot-based matches)
            try:
                elo_cur.execute(
                    "SELECT online_elo, user_display_name, online_event_elo FROM overall_standings WHERE user_id = ?",
                    (player_id_normalized,),
                )
                elo_row = elo_cur.fetchone()
                if elo_row:
                    player_elo = elo_row[0] if elo_row[0] else 1500
                    player_name_from_elo = elo_row[1]
                    event_elo = elo_row[2] if elo_row[2] else 1500
                    online_elo = player_elo
                    online_event_elo = event_elo
                    elo_cur.execute(
                        "SELECT COUNT(*) FROM overall_standings WHERE online_elo > ?", (player_elo,)
                    )
                    rank = elo_cur.fetchone()[0] + 1
            except sqlite3.OperationalError:
                pass

            # Get paper ELO from paper_standings for the source toggle
            try:
                elo_cur.execute(
                    "SELECT paper_elo, paper_event_elo FROM paper_standings WHERE user_id = ?",
                    (original_player_id,),
                )
                paper_row = elo_cur.fetchone()
                if paper_row:
                    paper_elo = paper_row[0] if paper_row[0] else 1500
                    paper_event_elo = paper_row[1] if paper_row[1] else 1500
            except sqlite3.OperationalError:
                pass

        # Determine displayed ELO/rank based on filter
        if event_filter == "lifetime":
            displayed_elo = player_elo
            displayed_rank = rank
        elif event_filter == "current":
            displayed_elo = event_elo
            # For current event, calculate rank among event participants
            try:
                # Get participants from match records
                match_conn_tmp = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
                match_cur_tmp = match_conn_tmp.cursor()
                if source == "web":
                    match_cur_tmp.execute("""
                        SELECT DISTINCT user_id FROM (
                            SELECT winner_id as user_id FROM match_reports_web WHERE timestamp >= ?
                            UNION
                            SELECT losser_id as user_id FROM match_reports_web WHERE timestamp >= ?
                        )
                    """, (event_start_date or "", event_start_date or ""))
                    web_participants = {str(row[0]) for row in match_cur_tmp.fetchall()}
                    match_conn_tmp.close()

                    elo_cur.execute(
                        "SELECT user_id, paper_event_elo FROM paper_standings WHERE paper_event_elo > ?",
                        (event_elo,),
                    )
                    displayed_rank = sum(1 for r in elo_cur.fetchall() if str(r[0]) in web_participants) + 1
                else:
                    match_cur_tmp.execute("""
                        SELECT DISTINCT user_id FROM (
                            SELECT winner_id as user_id FROM match_records WHERE timestamp >= ?
                            UNION
                            SELECT losser_id as user_id FROM match_records WHERE timestamp >= ?
                        )
                    """, (event_start_date or "", event_start_date or ""))
                    bot_participants = {row[0] for row in match_cur_tmp.fetchall()}
                    match_conn_tmp.close()

                    elo_cur.execute(
                        "SELECT user_id, event_elo FROM overall_standings WHERE event_elo > ?",
                        (event_elo,),
                    )
                    displayed_rank = sum(1 for r in elo_cur.fetchall() if r[0] in bot_participants) + 1
            except sqlite3.OperationalError:
                displayed_rank = 0
        elif archive_event_id is not None:
            # Get ELO from archived event standings (bot-only for now)
            try:
                elo_cur.execute(
                    "SELECT final_event_elo, final_rank FROM event_standings_archive WHERE event_id = ? AND user_id = ?",
                    (archive_event_id, player_id_normalized),
                )
                archive_row = elo_cur.fetchone()
                if archive_row:
                    displayed_elo = archive_row[0]
                    displayed_rank = archive_row[1]
            except sqlite3.OperationalError:
                pass  # Table may not exist

        elo_conn.close()
    except sqlite3.OperationalError:
        pass

    # Get player name - custom_display_name has highest priority
    player_name = None
    profile = None

    # Check custom_display_name first (user explicitly set this)
    try:
        from repositories.user_profiles import UserProfileRepository
        user_repo = UserProfileRepository()
        profile = user_repo.get_by_user_id(original_player_id)
        if not profile and original_player_id != player_id_normalized:
            profile = user_repo.get_by_user_id(player_id_normalized)
        if profile:
            if profile.get("custom_display_name"):
                player_name = profile["custom_display_name"]
            elif not player_name:
                player_name = profile["display_name"]
    except Exception:
        pass

    # Fallback: match records, ELO database
    if not player_name:
        if rows:
            first_match = rows[0]
            player_name = first_match[4] if first_match[0] else first_match[5]
        elif solo_rows:
            player_name = solo_rows[0][4]
        elif player_name_from_elo:
            player_name = player_name_from_elo

    # Fallback: get name from session if it's their profile
    if not player_name:
        logged_in_user_id = session.get("user_id")
        if logged_in_user_id is not None:
            logged_in_id_str = str(logged_in_user_id)
            if logged_in_id_str.startswith("google_"):
                logged_in_id_str = logged_in_id_str[7:]
            # If viewing their own profile, use session username
            if logged_in_id_str == str(player_id_normalized):
                player_name = session.get("username", "Unknown Player")

    # Player not found if no matches AND not in ELO database AND not in user_profiles AND not the logged-in user
    if not rows and not solo_rows and not player_name_from_elo and not player_name:
        return jsonify({"error": "Player not found"}), 404

    # Default player name if still not set
    if not player_name:
        player_name = "Unknown Player"

    # Split all_rows into ranked and casual for stats computation
    def _is_casual_row(row):
        return len(row) > 19 and row[19] in ("casual", "testing")

    ranked_stat_rows = [r for r in all_rows if not _is_casual_row(r)]
    casual_stat_rows = [r for r in all_rows if _is_casual_row(r)]

    # Calculate stats (ranked by default)
    total_matches = len(ranked_stat_rows)
    wins = sum(1 for row in ranked_stat_rows if row[0])
    losses = total_matches - wins
    win_rate = (wins / total_matches * 100) if total_matches > 0 else 0

    # Casual stats
    casual_total = len(casual_stat_rows)
    casual_wins = sum(1 for row in casual_stat_rows if row[0])
    casual_losses = casual_total - casual_wins
    casual_win_rate = (casual_wins / casual_total * 100) if casual_total > 0 else 0

    # First player stats (on the play)
    # New columns: winner_went_first (index 17), loser_went_first (index 18)
    # did_win (index 0): 1 if viewed player is winner, 0 if loser
    # Matches without play/draw data are excluded (both functions return False)
    # Filter to only include matches from 2-7-2026 forward for play/draw stats
    cutoff_date = "2026-02-07"
    play_draw_rows = [row for row in ranked_stat_rows if row[6] and str(row[6]) >= cutoff_date]
    casual_play_draw_rows = [row for row in casual_stat_rows if row[6] and str(row[6]) >= cutoff_date]

    def player_was_on_play(row):
        did_win = row[0]
        # Try new columns first (indices 17 and 18)
        winner_went_first = row[17] if len(row) > 17 else None
        loser_went_first = row[18] if len(row) > 18 else None

        # Use new columns if available
        if winner_went_first is not None or loser_went_first is not None:
            if did_win:
                # Player is the winner - check if winner went first
                return winner_went_first and "y" in str(winner_went_first).lower()
            else:
                # Player is the loser - check if loser went first
                return loser_went_first and "y" in str(loser_went_first).lower()

        # Fallback to old first_player column (for historical data)
        first_player = row[1]
        if not first_player:
            return False
        fp_lower = str(first_player).lower()
        # Winner went first
        if "y" in fp_lower:
            return did_win  # Player was on play only if they won
        else:
            # Loser went first
            return not did_win  # Player was on play only if they lost

    first_player_matches = sum(1 for row in play_draw_rows if player_was_on_play(row))
    first_player_wins = sum(1 for row in play_draw_rows if row[0] and player_was_on_play(row))
    first_player_win_rate = (
        (first_player_wins / first_player_matches * 100)
        if first_player_matches > 0
        else 0
    )

    # On the draw stats
    def player_was_on_draw(row):
        did_win = row[0]
        # Try new columns first (indices 17 and 18)
        winner_went_first = row[17] if len(row) > 17 else None
        loser_went_first = row[18] if len(row) > 18 else None

        # Use new columns if available
        if winner_went_first is not None or loser_went_first is not None:
            if did_win:
                # Player is the winner - on draw if winner did NOT go first
                return winner_went_first and "n" in str(winner_went_first).lower()
            else:
                # Player is the loser - on draw if loser did NOT go first
                return loser_went_first and "n" in str(loser_went_first).lower()

        # Fallback to old first_player column (for historical data)
        first_player = row[1]
        if not first_player:
            return False
        fp_lower = str(first_player).lower()
        # Winner went first
        if "y" in fp_lower:
            return not did_win  # Player was on draw only if they lost
        else:
            # Loser went first
            return did_win  # Player was on draw only if they won

    draw_matches = sum(1 for row in play_draw_rows if player_was_on_draw(row))
    draw_wins = sum(1 for row in play_draw_rows if row[0] and player_was_on_draw(row))
    draw_win_rate = (draw_wins / draw_matches * 100) if draw_matches > 0 else 0

    # Casual play/draw stats
    casual_fp_matches = sum(1 for row in casual_play_draw_rows if player_was_on_play(row))
    casual_fp_wins = sum(1 for row in casual_play_draw_rows if row[0] and player_was_on_play(row))
    casual_fp_win_rate = (casual_fp_wins / casual_fp_matches * 100) if casual_fp_matches > 0 else 0
    casual_draw_matches = sum(1 for row in casual_play_draw_rows if player_was_on_draw(row))
    casual_draw_wins = sum(1 for row in casual_play_draw_rows if row[0] and player_was_on_draw(row))
    casual_draw_win_rate = (casual_draw_wins / casual_draw_matches * 100) if casual_draw_matches > 0 else 0

    # Average match time (ranked)
    match_times = [
        float(row[3])
        for row in ranked_stat_rows
        if row[3] and str(row[3]).replace(".", "").isdigit()
    ]
    avg_match_time = sum(match_times) / len(match_times) if match_times else 0

    # Average match time (casual)
    casual_match_times = [
        float(row[3])
        for row in casual_stat_rows
        if row[3] and str(row[3]).replace(".", "").isdigit()
    ]
    casual_avg_match_time = sum(casual_match_times) / len(casual_match_times) if casual_match_times else 0

    # Avatar stats - only count the main avatar (type: "Avatar"), exclude sideboard
    avatar_stats = {}
    for row in all_rows:
        did_win = row[0]
        winner_json = row[13] if len(row) > 13 else None
        loser_json = row[14] if len(row) > 14 else None

        deck_json = winner_json if did_win else loser_json
        if not deck_json or deck_json == "{}":
            deck_json = row[2]

        if deck_json and deck_json != "{}":
            try:
                deck_data = json.loads(deck_json)
                if not deck_data or not deck_data.get("avatar"):
                    continue

                avatar_list = deck_data.get("avatar", [])
                if not avatar_list:
                    continue

                # Find the main avatar - must have type "Avatar" (not sideboard avatars)
                # For Imposter decks, this ensures we only count Imposter, not the extra avatars
                main_avatar_name = None
                for av in avatar_list:
                    if av and av.get("type") == "Avatar" and av.get("name"):
                        main_avatar_name = av.get("name")
                        break

                # Fallback: if no type field, use first avatar with a name
                if (
                    not main_avatar_name
                    and avatar_list[0]
                    and avatar_list[0].get("name")
                ):
                    main_avatar_name = avatar_list[0].get("name")

                if not main_avatar_name:
                    continue

                if main_avatar_name not in avatar_stats:
                    avatar_stats[main_avatar_name] = {"wins": 0, "losses": 0}

                if did_win:
                    avatar_stats[main_avatar_name]["wins"] += 1
                else:
                    avatar_stats[main_avatar_name]["losses"] += 1
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue

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

    # Opponent avatar stats - only count main avatar (type: "Avatar"), exclude sideboard
    opponent_avatar_stats = {}
    for row in all_rows:
        did_win = row[0]
        winner_json = row[13] if len(row) > 13 else None
        loser_json = row[14] if len(row) > 14 else None
        opponent_name = row[5] if did_win else row[4]
        opponent_id = row[11] if did_win else row[10] if len(row) > 10 else None

        opponent_avatar_name = None
        opponent_deck_json = loser_json if did_win else winner_json

        if opponent_deck_json and opponent_deck_json != "{}":
            try:
                deck_data = json.loads(opponent_deck_json)
                if deck_data and deck_data.get("avatar"):
                    avatar_list = deck_data.get("avatar", [])
                    # Find the main avatar - must have type "Avatar"
                    for av in avatar_list:
                        if av and av.get("type") == "Avatar" and av.get("name"):
                            opponent_avatar_name = av.get("name")
                            break
                    # Fallback: if no type field, use first avatar with a name
                    if (
                        not opponent_avatar_name
                        and avatar_list
                        and avatar_list[0]
                        and avatar_list[0].get("name")
                    ):
                        opponent_avatar_name = avatar_list[0].get("name")
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                pass

        if not opponent_avatar_name and opponent_name and opponent_id == 0:
            if "Opponent (" in opponent_name:
                try:
                    start = opponent_name.find("(") + 1
                    end = opponent_name.find(")")
                    if start > 0 and end > start:
                        opponent_avatar_name = opponent_name[start:end].strip()
                except (IndexError, ValueError):
                    pass
            else:
                opponent_avatar_name = opponent_name

        if not opponent_avatar_name:
            continue

        if opponent_avatar_name not in opponent_avatar_stats:
            opponent_avatar_stats[opponent_avatar_name] = {"wins": 0, "losses": 0}

        if did_win:
            opponent_avatar_stats[opponent_avatar_name]["wins"] += 1
        else:
            opponent_avatar_stats[opponent_avatar_name]["losses"] += 1

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

    # Winrate vs ELO brackets
    # Calculate opponent ELO at match time and group by bracket
    elo_bracket_stats = {
        "1700+": {"wins": 0, "losses": 0},
        "1600-1699": {"wins": 0, "losses": 0},
        "1500-1599": {"wins": 0, "losses": 0},
        "1400-1499": {"wins": 0, "losses": 0},
        "1300-1399": {"wins": 0, "losses": 0},
        "1200-1299": {"wins": 0, "losses": 0},
        "1199 or less": {"wins": 0, "losses": 0},
    }

    # Get opponent ELOs from database
    try:
        elo_conn = sqlite3.connect(str(ELO_DB_PATH))
        elo_cur = elo_conn.cursor()

        for row in all_rows:
            did_win = row[0]
            opponent_id = str(row[11]) if did_win else str(row[10])
            winner_elo_change = row[7] if row[7] else 0
            loser_elo_change = row[8] if row[8] else 0

            # Get opponent's current ELO
            opponent_elo = None
            if source == "web":
                # Query paper_standings for web matches
                try:
                    elo_cur.execute(
                        "SELECT paper_elo FROM paper_standings WHERE user_id = ?",
                        (opponent_id,)
                    )
                    opp_row = elo_cur.fetchone()
                    if opp_row:
                        opponent_elo = opp_row[0]
                except sqlite3.OperationalError:
                    pass
            else:
                # Query overall_standings for bot matches
                # Normalize opponent_id for bot matches (remove google_ prefix if present)
                opponent_id_normalized = opponent_id
                if opponent_id.startswith("google_"):
                    opponent_id_normalized = opponent_id[7:]

                try:
                    elo_cur.execute(
                        "SELECT elo FROM overall_standings WHERE user_id = ?",
                        (opponent_id_normalized,)
                    )
                    opp_row = elo_cur.fetchone()
                    if opp_row:
                        opponent_elo = opp_row[0]
                except sqlite3.OperationalError:
                    pass

            # If we have opponent ELO, categorize by bracket
            if opponent_elo is not None:
                if opponent_elo >= 1700:
                    bracket = "1700+"
                elif opponent_elo >= 1600:
                    bracket = "1600-1699"
                elif opponent_elo >= 1500:
                    bracket = "1500-1599"
                elif opponent_elo >= 1400:
                    bracket = "1400-1499"
                elif opponent_elo >= 1300:
                    bracket = "1300-1399"
                elif opponent_elo >= 1200:
                    bracket = "1200-1299"
                else:
                    bracket = "1199 or less"

                if did_win:
                    elo_bracket_stats[bracket]["wins"] += 1
                else:
                    elo_bracket_stats[bracket]["losses"] += 1

        elo_conn.close()
    except Exception as e:
        logger.error(f"Error calculating ELO bracket stats: {e}", exc_info=True)

    # Format ELO bracket stats for response
    elo_vs_brackets = []
    for bracket, stats in elo_bracket_stats.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            bracket_win_rate = (stats["wins"] / total * 100)
            elo_vs_brackets.append({
                "bracket": bracket,
                "wins": stats["wins"],
                "losses": stats["losses"],
                "total": total,
                "win_rate": round(bracket_win_rate, 1)
            })

    # Check ownership
    # Normalize logged_in_user_id for comparison (strip 'google_' prefix if present)
    logged_in_user_id = session.get("user_id")
    if logged_in_user_id is not None:
        logged_in_id_str = str(logged_in_user_id)
        if logged_in_id_str.startswith("google_"):
            logged_in_id_str = logged_in_id_str[7:]  # Remove 'google_' prefix
        # Compare as strings to avoid overflow with large IDs
        is_owner = logged_in_id_str == str(player_id_normalized)
    else:
        is_owner = False

    # API key grants owner-level access (for server-to-server calls)
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key in VALID_API_KEYS:
        is_owner = True

    # Admins have full access to all player profiles
    if is_admin():
        is_owner = True

    # Build match history with pagination
    # Split rows into ranked and casual based on match_type column (index 19)
    match_history = []
    casual_match_history = []
    sorted_rows = sorted(rows, key=lambda x: x[6] if x[6] else "", reverse=True)

    ranked_rows = [r for r in sorted_rows if not (len(r) > 19 and r[19] in ("casual", "testing"))]
    casual_rows = [r for r in sorted_rows if len(r) > 19 and r[19] in ("casual", "testing")]

    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    casual_page = request.args.get("casual_page", 1, type=int)

    # Validate pagination parameters
    page = max(1, page)  # Ensure page is at least 1
    per_page = min(max(10, per_page), 100)  # Limit per_page between 10 and 100
    casual_page = max(1, casual_page)

    # Calculate ranked pagination
    total_ranked_matches = len(ranked_rows)
    total_pages = (total_ranked_matches + per_page - 1) // per_page if total_ranked_matches > 0 else 1
    page = min(page, total_pages)  # Ensure page doesn't exceed total pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_rows = ranked_rows[start_idx:end_idx]

    # Calculate casual pagination
    total_casual_matches = len(casual_rows)
    total_casual_pages = (total_casual_matches + per_page - 1) // per_page if total_casual_matches > 0 else 1
    casual_page = min(casual_page, total_casual_pages)

    casual_start_idx = (casual_page - 1) * per_page
    casual_end_idx = casual_start_idx + per_page
    paginated_casual_rows = casual_rows[casual_start_idx:casual_end_idx]

    def _build_match_entry(row):
        """Convert a raw DB row into a match history dict."""
        did_win = row[0]
        opponent_name = row[5] if did_win else row[4]
        opponent_id = str(row[11]) if did_win else str(row[10])
        elo_change = row[7] if did_win else row[8]

        player_deck_url = None
        opponent_deck_url = None

        winner_deck_url = row[15] if len(row) > 15 else None
        loser_deck_url = row[16] if len(row) > 16 else None
        winner_json = row[13] if len(row) > 13 else None
        loser_json = row[14] if len(row) > 14 else None

        player_deck_url_check = winner_deck_url if did_win else loser_deck_url
        player_deck_json = winner_json if did_win else loser_json

        has_deck = False
        has_deck_json = False
        if player_deck_url_check and player_deck_url_check not in (
            "No URL provided",
            "Admin reported match",
            "{}",
            "",
            None,
        ) and str(player_deck_url_check).startswith("https://curiosa.io"):
            has_deck = True
        if player_deck_json and player_deck_json not in ("{}", "", None):
            has_deck = True
            has_deck_json = True

        player_avatar_name, deck_elements = _extract_deck_info(player_deck_json)

        opponent_deck_json = loser_json if did_win else winner_json
        opponent_avatar_name, opponent_elements = _extract_deck_info(opponent_deck_json)

        if is_owner:
            player_deck_url = winner_deck_url if did_win else loser_deck_url
            opponent_deck_url = loser_deck_url if did_win else winner_deck_url

        winner_went_first = row[17] if len(row) > 17 else None
        loser_went_first = row[18] if len(row) > 18 else None

        if winner_went_first is not None or loser_went_first is not None:
            if did_win:
                player_on_play = (
                    winner_went_first and "y" in str(winner_went_first).lower()
                )
            else:
                player_on_play = (
                    loser_went_first and "y" in str(loser_went_first).lower()
                )
        else:
            first_player_val = row[1]
            if first_player_val:
                fp_lower = str(first_player_val).lower()
                if "y" in fp_lower:
                    player_on_play = did_win
                else:
                    player_on_play = not did_win
            else:
                player_on_play = None

        return {
            "match_id": row[12],
            "opponent": opponent_name,
            "opponent_id": opponent_id,
            "result": "Win" if did_win else "Loss",
            "elo_change": elo_change if elo_change else 0,
            "date": row[6],
            "first_player": "Play"
            if player_on_play
            else "Draw"
            if player_on_play is False
            else None,
            "match_time": row[3] if row[3] else None,
            "replay_url": row[9] if row[9] else None,
            "player_deck_url": player_deck_url,
            "opponent_deck_url": opponent_deck_url,
            "has_deck": has_deck,
            "has_deck_json": has_deck_json,
            "match_type": row[19] if len(row) > 19 and row[19] else "ranked",
            "player_avatar": player_avatar_name,
            "deck_elements": deck_elements,
            "opponent_avatar": opponent_avatar_name,
            "opponent_elements": opponent_elements,
        }

    for row in paginated_rows:
        match_history.append(_build_match_entry(row))

    for row in paginated_casual_rows:
        casual_match_history.append(_build_match_entry(row))

    # Build lightweight ELO history from ALL ranked matches (for the chart)
    elo_history = []
    for row in ranked_rows:
        did_win = row[0]
        elo_change = row[7] if did_win else row[8]
        if not elo_change or not row[6]:
            continue
        opponent_name = row[5] if did_win else row[4]
        elo_history.append({
            "date": row[6],
            "elo_change": elo_change,
            "result": "Win" if did_win else "Loss",
            "opponent": opponent_name,
        })

    # Recent decks - group matches by deck URL to calculate win rates
    recent_decks = []
    deck_stats = {}  # deck_url -> {wins, losses, avatar, deck_name, last_date}

    for row in all_rows:
        did_win = row[0]
        winner_deck_url = row[15] if len(row) > 15 else row[9]
        loser_deck_url = row[16] if len(row) > 16 else None
        winner_json = row[13] if len(row) > 13 else row[2]
        loser_json = row[14] if len(row) > 14 else None

        player_deck_url = winner_deck_url if did_win else loser_deck_url
        player_deck_json = winner_json if did_win else loser_json

        if not player_deck_url or player_deck_url in (
            "No URL provided",
            "Admin reported match",
            "{}",
        ) or not str(player_deck_url).startswith("https://curiosa.io"):
            continue

        # Normalize URL by stripping query parameters (e.g. ?tab=view)
        player_deck_url = player_deck_url.split("?")[0]

        # Initialize deck stats if first time seeing this URL
        if player_deck_url not in deck_stats:
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

            deck_stats[player_deck_url] = {
                "wins": 0,
                "losses": 0,
                "avatar": avatar_name,
                "deck_name": deck_name,
                "last_date": row[6],
            }

        # Update win/loss count
        if did_win:
            deck_stats[player_deck_url]["wins"] += 1
        else:
            deck_stats[player_deck_url]["losses"] += 1

        # Update last_date if this match is more recent
        if row[6] and (not deck_stats[player_deck_url]["last_date"] or row[6] > deck_stats[player_deck_url]["last_date"]):
            deck_stats[player_deck_url]["last_date"] = row[6]

    # Convert to list and sort by most recent usage
    for deck_url, stats in sorted(deck_stats.items(), key=lambda x: x[1]["last_date"] or "", reverse=True):
        total_games = stats["wins"] + stats["losses"]
        deck_win_rate = (stats["wins"] / total_games * 100) if total_games > 0 else 0

        recent_decks.append(
            {
                "url": deck_url,
                "avatar": stats["avatar"],
                "deck_name": stats["deck_name"],
                "date": stats["last_date"],
                "wins": stats["wins"],
                "losses": stats["losses"],
                "win_rate": round(deck_win_rate, 1),
                "total_games": total_games,
            }
        )

        if len(recent_decks) >= 10:
            break

    # Recorded games (owner only)
    recorded_games = []
    sorted_solo_rows = sorted(
        solo_rows, key=lambda x: x[6] if x[6] else "", reverse=True
    )
    for row in sorted_solo_rows[:50]:
        did_win = row[0]
        opponent_name = row[5]
        deck_url = row[9]

        recorded_games.append(
            {
                "report_id": row[12],
                "opponent": opponent_name,
                "result": "Win" if did_win else "Loss",
                "date": row[6],
                "first_player": "Play"
                if row[1] and "y" in str(row[1]).lower()
                else "Draw",
                "match_time": row[3] if row[3] else None,
                "deck_url": deck_url,
            }
        )

    # Check if user has set a custom display name (reuse profile fetched earlier)
    has_custom_display_name = bool(profile and profile.get("custom_display_name")) if profile else False

    # Fetch limited arena stats
    limited_stats = _get_limited_stats(player_id_normalized)

    admin = is_admin()
    show_lifetime = admin or is_owner

    return jsonify(
        {
            "id": player_id_normalized,
            "name": player_name,
            "elo": player_elo if show_lifetime else None,
            "event_elo": event_elo,
            "displayed_elo": displayed_elo if event_filter != "lifetime" or show_lifetime else event_elo,
            "rank": rank if show_lifetime else None,
            "displayed_rank": displayed_rank if event_filter != "lifetime" or show_lifetime else 0,
            "event_filter": event_filter,
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
            "casual_stats": {
                "wins": casual_wins,
                "losses": casual_losses,
                "win_rate": round(casual_win_rate, 1),
                "total": casual_total,
                "avg_match_time": round(casual_avg_match_time, 1),
                "on_play_wins": casual_fp_wins,
                "on_play_matches": casual_fp_matches,
                "on_play_win_rate": round(casual_fp_win_rate, 1),
                "on_draw_wins": casual_draw_wins,
                "on_draw_matches": casual_draw_matches,
                "on_draw_win_rate": round(casual_draw_win_rate, 1),
            },
            "avatar_performance": avatar_performance if is_owner else [],
            "avatar_matchups": avatar_matchups if is_owner else [],
            "recent_decks": recent_decks,
            "elo_history": elo_history,
            "matches": match_history,
            "casual_matches": casual_match_history,
            "recorded_games": recorded_games if is_owner else [],
            "is_owner": is_owner,
            "is_admin": is_admin(),
            "has_custom_display_name": has_custom_display_name,
            "elo_vs_brackets": elo_vs_brackets,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_matches": total_ranked_matches,
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
            "casual_pagination": {
                "current_page": casual_page,
                "per_page": per_page,
                "total_matches": total_casual_matches,
                "total_pages": total_casual_pages,
                "has_previous": casual_page > 1,
                "has_next": casual_page < total_casual_pages,
            },
            # Dual ELO system fields
            "elo_source": source,
            "has_web_matches": has_web_matches,
            "has_bot_matches": has_bot_matches,
            "paper_elo": paper_elo,
            "online_elo": online_elo,
            "paper_event_elo": paper_event_elo,
            "online_event_elo": online_event_elo,
            "limited": limited_stats,
        }
    )


@players_bp.route("/player/<player_id>/set-display-name", methods=["POST"])
def set_display_name(player_id):
    """Set a custom display name for the logged-in user (one-time only)."""
    logger.info(f"set_display_name API called: player_id={player_id}")

    # Verify session auth - user must be logged in as this player
    logged_in_user_id = session.get("user_id")
    if logged_in_user_id is None:
        return jsonify({"error": "Authentication required"}), 401

    auth_provider = session.get("auth_provider", "discord")
    logger.info(f"set_display_name: logged_in_user_id={logged_in_user_id}, auth_provider={auth_provider}")

    # Normalize IDs for comparison
    original_player_id = str(player_id)
    logged_in_id_str = str(logged_in_user_id)
    player_id_normalized = original_player_id
    if original_player_id.startswith("google_"):
        player_id_normalized = original_player_id[7:]
    logged_in_normalized = logged_in_id_str
    if logged_in_id_str.startswith("google_"):
        logged_in_normalized = logged_in_id_str[7:]

    if logged_in_normalized != player_id_normalized:
        return jsonify({"error": "You can only set your own display name"}), 403

    data = request.get_json()
    if not data or not data.get("display_name"):
        return jsonify({"error": "Display name is required"}), 400

    new_name = data["display_name"].strip()
    logger.info(f"set_display_name: Attempting to set display name to '{new_name}'")

    # Validate length
    if len(new_name) < 1 or len(new_name) > 32:
        return jsonify({"error": "Display name must be 1-32 characters"}), 400

    # Validate characters (alphanumeric, spaces, hyphens, underscores, periods)
    if not re.match(r'^[\w\s\-\.]+$', new_name):
        return jsonify({"error": "Display name can only contain letters, numbers, spaces, hyphens, underscores, and periods"}), 400

    try:
        profile_repo = UserProfileRepository()

        # Try to set the custom display name (fails if already set)
        profile_user_id = logged_in_id_str
        success = profile_repo.set_custom_display_name(profile_user_id, auth_provider, new_name)
        if not success:
            return jsonify({"error": "Display name has already been set"}), 409

        logger.info(f"User {logged_in_id_str} set custom display name to '{new_name}'")

        # Update display name in leaderboard standings and match records
        # These are cosmetic updates - don't fail if they error
        from repositories.elo import EloRepository
        from repositories.matches import MatchRepository

        try:
            elo_repo = EloRepository()
            match_repo = MatchRepository()

            # Update bot standings (uses normalized ID without google_ prefix)
            elo_repo.rename_player(player_id_normalized, new_name)
            match_repo.rename_player_in_matches(player_id_normalized, new_name)

            # Update paper standings (uses original ID with google_ prefix for Google users)
            elo_repo.rename_paper_player(str(logged_in_id_str), new_name)
            match_repo.rename_player_in_web_matches(str(logged_in_id_str), new_name)
        except Exception as e:
            # Log the error but don't fail the whole operation
            # The custom display name was successfully set, which is what matters
            logger.warning(f"Error updating display name in ELO/match tables (non-fatal): {e}", exc_info=True)

        return jsonify({"success": True, "display_name": new_name})

    except Exception as e:
        logger.error(f"Error setting display name: {e}", exc_info=True)
        return jsonify({"error": "Failed to set display name"}), 500
