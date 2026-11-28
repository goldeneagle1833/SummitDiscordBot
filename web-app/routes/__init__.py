"""Route blueprints for the web application."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """Register all blueprints with the Flask app."""
    from routes.auth import auth_bp
    from routes.api import api_bp
    from routes.og_preview import og_preview_bp
    from routes.mcp_oauth import mcp_oauth_bp, mcp_wellknown_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(og_preview_bp)
    # Sign-in for AI apps (Summit MCP server): OAuth endpoints + discovery document
    app.register_blueprint(mcp_oauth_bp, url_prefix="/auth/mcp")
    app.register_blueprint(mcp_wellknown_bp)
