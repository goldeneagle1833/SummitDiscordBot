"""Standardized JSON error responses for the API.

Routes can either raise ``ApiError`` (preferred for new code) or call
``api_error(...)`` to build a Flask response directly. The shape is:

    {"error": {"message": str, "code": str | None}}

Register the global handler once during app setup with ``register_error_handlers(app)``.
"""

from __future__ import annotations

import logging
from typing import Tuple

from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Raise to return a structured JSON error from a route."""

    def __init__(self, message: str, status: int = 400, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def api_error(message: str, status: int = 400, code: str | None = None) -> Tuple[Response, int]:
    """Build a (jsonify, status) tuple for a structured error response."""
    payload = {"error": {"message": message, "code": code}}
    return jsonify(payload), status


def register_error_handlers(app: Flask) -> None:
    """Register JSON error handlers on the Flask app."""

    @app.errorhandler(ApiError)
    def _handle_api_error(err: ApiError):
        return api_error(err.message, err.status, err.code)

    @app.errorhandler(HTTPException)
    def _handle_http(err: HTTPException):
        return api_error(err.description or err.name, err.code or 500)

    @app.errorhandler(Exception)
    def _handle_unexpected(err: Exception):
        logger.exception("Unhandled exception in request")
        return api_error("Internal server error", 500, code="internal_error")
