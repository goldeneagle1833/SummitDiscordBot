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
    conn = sqlite3.connect("../discord-bot/utils/elo.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT user_display_name, elo
        FROM overall_standings
        ORDER BY elo DESC
    """)
    rows = cur.fetchall()
    conn.close()
    leaderboard = [{"name": row[0], "elo": row[1]} for row in rows]
    return jsonify(leaderboard)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
