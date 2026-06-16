"""
Summit Web Application - Refactored with layered architecture.

This is the application factory that ties together:
- Routes (API layer)
- Services (Business logic layer)
- Repositories (Data access layer)
"""

import sys
import logging
from datetime import timedelta
from pathlib import Path
from flask import Flask

# Import web-app config (named webapp_config to avoid conflict with discord-bot's config)
import webapp_config

# Add discord-bot to path for shared utilities (database functions, etc.)
_bot_path = str(Path(__file__).parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.append(_bot_path)  # append, not insert, to keep web-app priority

from utils.version import APP_VERSION
from utils.auth import get_current_user, is_admin, is_curio_editor
from routes import register_blueprints
from migrations.create_match_reports_web import create_match_reports_web_table
from migrations.add_season_id_to_match_reports_web import migrate as migrate_season_id
from migrations.create_analytics_tables import create_analytics_tables
from migrations.create_explorer_tables import create_explorer_tables
from migrations.create_rumble_tables import create_rumble_tables
from migrations.create_external_matches_table import create_external_matches_table
from migrations.create_deck_builder_tables import create_deck_builder_tables

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.secret_key = webapp_config.SECRET_KEY

    # Session cookie persistence (30 days) - prevents logout on mobile/browser close
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['SESSION_COOKIE_SECURE'] = True      # HTTPS only (Cloudflare)
    app.config['SESSION_COOKIE_HTTPONLY'] = True     # No JS access
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'   # CSRF protection

    # Force template reloading (disable caching)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Ensure required tables exist and run migrations
    try:
        create_match_reports_web_table()
        migrate_season_id()
    except Exception as e:
        logger.error(f"Failed to ensure match_reports_web table: {e}")

    try:
        create_analytics_tables()
    except Exception as e:
        logger.error(f"Failed to ensure analytics tables: {e}")

    try:
        create_explorer_tables()
    except Exception as e:
        logger.error(f"Failed to ensure explorer tables: {e}")

    try:
        create_rumble_tables()
    except Exception as e:
        logger.error(f"Failed to ensure rumble tables: {e}")

    try:
        create_external_matches_table()
    except Exception as e:
        logger.error(f"Failed to ensure external_matches table: {e}")

    try:
        create_deck_builder_tables()
    except Exception as e:
        logger.error(f"Failed to ensure deck_builder tables: {e}")

    # Register all blueprints
    register_blueprints(app)

    # Register static file routes
    register_static_routes(app)

    # Register context processor
    @app.context_processor
    def inject_globals():
        """Make current user and app version available to all templates."""
        from services.pilots import is_pilot_active

        admin = is_admin()
        return {
            "current_user": get_current_user(),
            "app_version": APP_VERSION,
            "is_admin": admin,
            "is_curio_editor": is_curio_editor(),
            "show_limited_leaderboard": admin or is_pilot_active("limited_leaderboard"),
        }

    logger.info(f"Application initialized, version: {APP_VERSION}")
    return app


def register_static_routes(app: Flask) -> None:
    """Register routes for serving static files."""
    from flask import send_from_directory

    @app.route("/avatar-images/<path:filename>")
    def avatar_images(filename):
        return send_from_directory(webapp_config.AVATAR_IMAGES_DIR, filename)

    @app.route("/card-images/<path:filename>")
    def card_images(filename):
        response = send_from_directory(webapp_config.CARD_IMAGES_DIR, filename)
        response.cache_control.max_age = 86400 * 30  # 30 days
        response.cache_control.public = True
        return response


# Create the app instance
app = create_app()

if __name__ == "__main__":
    import os
    # SECURITY: Only enable debug mode explicitly via environment variable
    # Never expose debug mode on all interfaces in production
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    host = "127.0.0.1" if not debug_mode else os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(debug=debug_mode, host=host, port=port)
