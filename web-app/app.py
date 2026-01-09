"""
Summit Web Application - A lightweight Flask web app
"""

from flask import Flask, render_template, jsonify
import sqlite3
import os
import json
from pathlib import Path

app = Flask(__name__)

# Path to top-8 event data
TOP_8_DIR = Path(__file__).parent / "top-8-decks-by-event"


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


@app.route("/avatars")
def avatars():
    """Avatar stats page"""
    return render_template("pages/avatars.html")


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


@app.route("/deck-help")
def deck_help():
    """Deck help and resources page"""
    return render_template("pages/deck_help.html")


@app.route("/top-8")
def top_8():
    """Top 8 decks by event page - lists all events"""
    events = []

    if TOP_8_DIR.exists():
        for folder in sorted(TOP_8_DIR.iterdir(), reverse=True):
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
        for folder in sorted(TOP_8_DIR.iterdir(), reverse=True):
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


# Player profile page
@app.route("/player/<player_id>")
def player_profile(player_id):
    return render_template("pages/player.html", player_id=player_id)


# Player API endpoint
@app.route("/api/player/<player_id>")
def player_api(player_id):
    import json

    # Get detailed match data from match_records db first
    conn = sqlite3.connect("../discord-bot/match_records.db")
    cur = conn.cursor()

    # Get all matches for detailed stats
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

    # Avatar stats
    avatar_stats = {}
    for row in rows:
        if row[2] and row[2] != "{}":  # Skip empty JSON objects
            try:
                deck_data = json.loads(row[2])
                # Skip if deck_data is empty or has no avatar
                if not deck_data or not deck_data.get("avatar"):
                    continue

                avatar = deck_data.get("avatar", [])
                if not avatar or not avatar[0] or not avatar[0].get("name"):
                    continue

                avatar_name = avatar[0].get("name")

                if avatar_name not in avatar_stats:
                    avatar_stats[avatar_name] = {"wins": 0, "losses": 0}

                if row[0]:  # did_win
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

    # Build match history (last 50 matches)
    match_history = []
    for row in rows[:50]:
        did_win = row[0]
        opponent_name = row[5] if did_win else row[4]
        # When player won, opponent is the loser (losser_id at index 11)
        # When player lost, opponent is the winner (winner_id at index 10)
        opponent_id = str(row[11]) if did_win else str(row[10])
        elo_change = row[7] if did_win else row[8]
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
            }
        )

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
            "avatar_performance": avatar_performance,
            "matches": match_history,
        }
    )


@app.route("/api/avatars")
def avatars_api():
    """API endpoint for global avatar stats from all matches with deck data"""
    import json

    try:
        conn = sqlite3.connect("../discord-bot/match_records.db")
        cur = conn.cursor()

        # Get all matches with deck data
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
        conn.close()
    except sqlite3.OperationalError:
        # Table doesn't exist or database not found
        return jsonify([])

    # Calculate avatar stats across all matches
    avatar_stats = {}
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
