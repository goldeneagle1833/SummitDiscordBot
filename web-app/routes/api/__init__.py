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

api_bp.register_blueprint(leaderboard_bp)
api_bp.register_blueprint(matches_bp)
api_bp.register_blueprint(players_bp)
api_bp.register_blueprint(avatars_bp)
api_bp.register_blueprint(cards_bp)
api_bp.register_blueprint(games_bp)
api_bp.register_blueprint(rules_bp)
api_bp.register_blueprint(misc_bp)
api_bp.register_blueprint(streamers_bp)
