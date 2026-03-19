"""API route blueprints."""

from flask import Blueprint

api_bp = Blueprint("api", __name__)

# Import and register sub-blueprints
from routes.api.leaderboard import leaderboard_bp
from routes.api.matches import matches_bp
from routes.api.players import players_bp
from routes.api.avatars import avatars_bp
from routes.api.cards import cards_bp
from routes.api.games import games_bp
from routes.api.rules import rules_bp
from routes.api.misc import misc_bp
from routes.api.streamers import streamers_bp
from routes.api.external_matches import external_matches_bp
from routes.api.metagame import metagame_bp
from routes.api.admin import admin_bp
from routes.api.match_reporting import match_reporting_bp
from routes.api.curios import curios_bp

api_bp.register_blueprint(leaderboard_bp)
api_bp.register_blueprint(matches_bp)
api_bp.register_blueprint(players_bp)
api_bp.register_blueprint(avatars_bp)
api_bp.register_blueprint(cards_bp)
api_bp.register_blueprint(games_bp)
api_bp.register_blueprint(rules_bp)
api_bp.register_blueprint(misc_bp)
api_bp.register_blueprint(streamers_bp)
api_bp.register_blueprint(external_matches_bp)
api_bp.register_blueprint(metagame_bp)
api_bp.register_blueprint(admin_bp)
api_bp.register_blueprint(match_reporting_bp, url_prefix="/match-report")
api_bp.register_blueprint(curios_bp, url_prefix="/curios")
