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


@app.route("/api/status")
def api_status():
    """Simple API endpoint to check if the server is running"""
    return jsonify({"status": "online", "message": "Summit Web App is running!"})


# Leaderboard API endpoint
@app.route("/api/leaderboard")
def leaderboard():
    # Get ELO standings
    conn = sqlite3.connect("../elo.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, user_display_name, elo
        FROM overall_standings
        ORDER BY elo DESC
    """)
    rows = cur.fetchall()
    conn.close()

    # Get win/loss records from match_records
    conn = sqlite3.connect("../match_records.db")
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
                "id": row[0],
                "name": row[1],
                "elo": row[2],
                "wins": wins,
                "losses": losses,
            }
        )

    conn.close()
    return jsonify(leaderboard_data)


# Player profile page
@app.route("/player/<int:player_id>")
def player_profile(player_id):
    return render_template("player.html", player_id=player_id)


# Player API endpoint
@app.route("/api/player/<int:player_id>")
def player_api(player_id):
    # Get player info from ELO db
    conn = sqlite3.connect("../elo.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, user_display_name, elo
        FROM overall_standings
        WHERE user_id = ?
    """,
        (player_id,),
    )
    player_row = cur.fetchone()
    conn.close()

    if not player_row:
        return jsonify({"error": "Player not found"}), 404

    # Get match history from match_records db
    conn = sqlite3.connect("../match_records.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT winner_id, winner_display_name, losser_id, losser_display_name,
               timestamp, winner_elo_change, loser_elo_change
        FROM match_records
        WHERE winner_id = ? OR losser_id = ?
        ORDER BY timestamp DESC
        LIMIT 50
    """,
        (player_id, player_id),
    )
    matches = cur.fetchall()
    conn.close()

    # Calculate stats
    wins = sum(1 for m in matches if m[0] == player_id)
    losses = sum(1 for m in matches if m[2] == player_id)

    match_history = []
    for m in matches:
        is_winner = m[0] == player_id
        opponent_name = m[3] if is_winner else m[1]
        elo_change = m[5] if is_winner else m[6]
        match_history.append(
            {
                "opponent": opponent_name,
                "result": "Win" if is_winner else "Loss",
                "elo_change": elo_change if elo_change else 0,
                "date": m[4],
            }
        )

    return jsonify(
        {
            "id": player_row[0],
            "name": player_row[1],
            "elo": player_row[2],
            "wins": wins,
            "losses": losses,
            "matches": match_history,
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
