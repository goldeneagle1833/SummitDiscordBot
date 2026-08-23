"""Authenticated relay between Sorcery Online and the loopback bot API."""

import os

import requests
from flask import Blueprint, jsonify, request

import webapp_config
from utils.api_auth import require_api_key


matchmaking_bp = Blueprint("matchmaking", __name__)


def matchmaking_api_key(view):
    decorated = require_api_key(view)
    decorated._auth_required = True
    return decorated


def _relay(method, path, payload=None):
    base_url = os.getenv("MATCHMAKING_BOT_API_URL", "http://127.0.0.1:8765").rstrip("/")
    try:
        response = requests.request(
            method,
            f"{base_url}{path}",
            json=payload,
            headers={"X-API-Key": webapp_config.DRAFT_SORCERY_API_KEY},
            timeout=float(os.getenv("MATCHMAKING_BOT_API_TIMEOUT", "9")),
        )
    except requests.RequestException:
        return jsonify({"membership": "unavailable", "queues": [], "result": None}), 503
    if response.status_code >= 500:
        return jsonify({"membership": "unavailable", "queues": [], "result": None}), 503
    try:
        body = response.json()
    except ValueError:
        body = {"error": response.text.strip() or "Matchmaking request failed"}
    return jsonify(body), response.status_code


@matchmaking_bp.get("/users/<user_id>/status")
@matchmaking_api_key
def status(user_id):
    return _relay("GET", f"/users/{user_id}/status")


@matchmaking_bp.post("/users/<user_id>/queues")
@matchmaking_api_key
def join_queue(user_id):
    return _relay("POST", f"/users/{user_id}/queues", request.get_json(silent=True) or {})


@matchmaking_bp.delete("/users/<user_id>/queues")
@matchmaking_api_key
def leave_queues(user_id):
    return _relay("DELETE", f"/users/{user_id}/queues")


@matchmaking_bp.post("/users/<user_id>/results/<result_id>/ack")
@matchmaking_api_key
def acknowledge_result(user_id, result_id):
    return _relay("POST", f"/users/{user_id}/results/{result_id}/ack")
