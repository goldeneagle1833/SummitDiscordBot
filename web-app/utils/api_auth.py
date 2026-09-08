"""API key authentication for external service integrations."""

import hmac
from functools import wraps

from flask import jsonify, request

import webapp_config


def require_api_key(f):
    """Decorator that validates the X-API-Key header against the configured Draft Sorcery key."""

    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != webapp_config.DRAFT_SORCERY_API_KEY:
            return jsonify({"success": False, "error": "Invalid API key"}), 401
        return f(*args, **kwargs)

    return decorated


def require_integration_api_key(f):
    """Accept the dedicated Sorcery key or an existing general integration key."""

    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        if api_key and api_key.startswith("Bearer "):
            api_key = api_key[7:]
        accepted_keys = [
            key for key in [webapp_config.DRAFT_SORCERY_API_KEY, *webapp_config.VALID_API_KEYS]
            if key
        ]
        if not api_key or not any(
            hmac.compare_digest(api_key, accepted_key)
            for accepted_key in accepted_keys
        ):
            return jsonify({"success": False, "error": "Invalid API key"}), 401
        return f(*args, **kwargs)

    return decorated
