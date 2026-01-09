"""
Summit Web Application - A lightweight Flask web app
"""

from flask import Flask, render_template, jsonify
import sqlite3

app = Flask(__name__)


@app.route("/")
def home():
    """Home page"""
    return render_template("index.html")


@app.route("/about")
def about():
    """About page"""
    return render_template("about.html")


@app.route("/avatars")
def avatars():
    """Avatar stats page"""
    return render_template("avatars.html")


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
    return render_template("player.html", player_id=player_id)


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
        elo_change = row[7] if did_win else row[8]
        match_history.append(
            {
                "match_id": row[10] if len(row) > 10 and row[10] else None,
                "opponent": opponent_name,
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
