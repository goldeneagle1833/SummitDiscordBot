"""Route blueprints for the web application."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask app."""
    from routes.auth import auth_bp
    from routes.api import api_bp
    from routes.og_preview import og_preview_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(og_preview_bp, url_prefix="/og")
