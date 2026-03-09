"""
Summit Web Application - Refactored with layered architecture.

This is the application factory that ties together:
- Routes (API layer)
- Services (Business logic layer)
- Repositories (Data access layer)
"""

import sys
import logging
from pathlib import Path
from flask import Flask

# Import web-app config (named webapp_config to avoid conflict with discord-bot's config)
import webapp_config

# Add discord-bot to path for shared utilities (database functions, etc.)
_bot_path = str(Path(__file__).parent.parent / "discord-bot")
if _bot_path not in sys.path:
    sys.path.append(_bot_path)  # append, not insert, to keep web-app priority

# Add SorceryAI to path
_sorcery_ai_path = str(Path(__file__).parent.parent / "SorceryAI")
if _sorcery_ai_path not in sys.path:
    sys.path.append(_sorcery_ai_path)

from utils.version import APP_VERSION
from utils.auth import get_current_user, is_admin
from routes import register_blueprints

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

    # Force template reloading (disable caching)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Register all blueprints
    register_blueprints(app)

    # Register static file routes
    register_static_routes(app)

    # Register context processor
    @app.context_processor
    def inject_globals():
        """Make current user and app version available to all templates."""
        return {
            "current_user": get_current_user(),
            "app_version": APP_VERSION,
            "is_admin": is_admin(),
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
        return send_from_directory(webapp_config.CARD_IMAGES_DIR, filename)


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
