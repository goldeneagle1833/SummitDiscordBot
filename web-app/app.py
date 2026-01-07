"""
Summit Web Application - A lightweight Flask web app
"""

from flask import Flask, render_template, jsonify

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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
