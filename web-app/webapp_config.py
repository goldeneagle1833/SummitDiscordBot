"""Configuration settings for the web application."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from discord-bot/.env (shared config)
_env_path = Path(__file__).parent.parent / "discord-bot" / ".env"
load_dotenv(_env_path)

# Base paths
BASE_DIR = Path(__file__).parent
BOT_DIR = BASE_DIR.parent / "discord-bot"
TOP_8_DIR = BASE_DIR / "top-8-decks-by-event"
CARD_IMAGES_DIR = BASE_DIR / "card_images"
AVATAR_IMAGES_DIR = BASE_DIR / "templates" / "avatar_imgs"
ALL_CARDS_PATH = BASE_DIR / "curiosa-io-tools" / "All_Cards_Array.json"

# Database paths
# Can be overridden via environment variables in production
ELO_DB_PATH = Path(os.environ.get("ELO_DB_PATH", BOT_DIR / "elo.db"))
MATCH_RECORDS_DB_PATH = Path(
    os.environ.get("MATCH_RECORDS_DB_PATH", BOT_DIR / "match_records.db")
)
FART_SCORES_DB_PATH = Path(
    os.environ.get("FART_SCORES_DB_PATH", BOT_DIR / "fart_scores.db")
)
COMMUNITY_DB_PATH = Path(os.environ.get("COMMUNITY_DB_PATH", BOT_DIR / "community.db"))
ANALYTICS_DB_PATH = Path(os.environ.get("ANALYTICS_DB_PATH", BASE_DIR / "analytics.db"))

# Upload directories
STATIC_DIR = BASE_DIR / "static"
CURIO_UPLOADS_DIR = STATIC_DIR / "uploads" / "curios"
CURIO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
BANNER_UPLOADS_DIR = STATIC_DIR / "uploads" / "banners"
BANNER_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Flask configuration
# SECURITY: SECRET_KEY must be set in production via environment variable
# In development, a random key is generated (sessions won't persist across restarts)
_secret_key_env = os.environ.get("SECRET_KEY")
if _secret_key_env:
    SECRET_KEY = _secret_key_env
elif (
    os.environ.get("FLASK_ENV") == "production" or os.environ.get("FLASK_DEBUG") == "0"
):
    raise ValueError(
        "SECURITY ERROR: SECRET_KEY environment variable must be set in production. "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
    )
else:
    # Development only: generate random key (sessions reset on restart)
    import secrets

    SECRET_KEY = secrets.token_hex(32)
    print(
        "WARNING: Using randomly generated SECRET_KEY. Set SECRET_KEY env var for persistent sessions."
    )

# Frontend URL - used for post-login redirects back to the React app
# In dev, React runs on :5173; in production it's the same origin
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# Discord OAuth configuration
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.environ.get(
    "DISCORD_REDIRECT_URI", "http://localhost:5000/auth/discord/callback"
)

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/google/callback"
)

# Admin Discord IDs - full access to all features in production
# Set via ADMIN_IDS env var as comma-separated list
ADMINS = [id.strip() for id in os.environ.get("ADMIN_IDS", "").split(",") if id.strip()]

# Curio Tracking editors - can add/edit/delete curio entries (no other admin access)
# Set via CURIO_EDITOR_IDS env var as comma-separated list
CURIO_EDITORS = [id.strip() for id in os.environ.get("CURIO_EDITOR_IDS", "").split(",") if id.strip()]

# API Key configuration for external integrations
API_KEYS_ENV = os.environ.get("API_KEYS", os.environ.get("API_KEY", ""))
VALID_API_KEYS = [key.strip() for key in API_KEYS_ENV.split(",") if key.strip()]

# Draft Sorcery API key for server-to-server limited arena endpoints
DRAFT_SORCERY_API_KEY = os.environ.get("DRAFT_SORCERY_API_KEY", os.environ.get("REALMSDRAFT_API_KEY", ""))

# Event star ratings (1-3 stars)
EVENT_RATINGS = {
    "ColumbusExplor2025": 1,
    "CortCup2024Stats": 2,
    "EU Crossroads 2025": 3,
    "Explorer96": 1,
    "GenCon2023Stats": 3,
    "GenCon2024Stats": 3,
    "Gencon2025": 3,
    "Houston SCGcon 2025 Crossroads": 3,
    "King of the Realm Cornerstone in NYC - 2025": 1,
    "OchoaDecklists": 1,
    "SCG CON Baltimore 2025 Crossroads": 3,
    "SCG Con Alanta 2026": 1,
    "SCG Con Portland 2026": 1,
    "SCG Con Vegas 2025 Crossroads": 3,
    "SORCERY CON": 3,
    "Sorcery Con 2024": 3,
    "SorceryCon 2024 stats": 3,
    "Sorcery Con Constructed 2026": 3,
    "Sorcery Con Limited 2026": 3,
    "Every one at Sorcery Con Constructed 2026": 3,
    "Top 32 Sorcery Con Constructed 2026": 3,
    "Top 64 Sorcery Con Constructed 2026": 3,
    "SS2": 1,
    "Season6TTSLeage": 1,
    "SorcerersSummit": 2,
    "SorceryFest2025": 2,
    "Sydney Cornerstone Top 4 2025": 1,
    "TTSLeague2023champions": 1,
    "TTSLeagueS3": 1,
    "TTSLeagueS7topCut": 1,
    "UnlandCup25": 1,
    "Sorcerers Summit 'Bottom' 5 avatars": 1,
    "Summit Gothic Season 1 2026": 3,
}

# Event name display mappings
EVENT_NAME_MAPPINGS = {
    "ColumbusExplor2025": "Columbus Explorer 2025",
    "CortCup2024Stats": "Cort Cup 2024",
    "Explorer96": "Explorer 9.6",
    "GenCon2023Stats": "Gen Con 2023",
    "GenCon2024Stats": "Gen Con 2024",
    "Gencon2025": "Gen Con 2025",
    "OchoaDecklists": "Ochoa Decklists",
    "SCGCON2025": "SCG CON 2025",
    "Season6TTSLeage": "Season 6 TTS League",
    "SorcerersSummit": "Sorcerers Summit",
    "SORCERY CON": "Sorcery Con",
    "SorceryCon 2024 stats": "Sorcery Con 2024",
    "SorceryFest2025": "Sorcery Fest 2025",
    "SS2": "Sorcerers Summit 2",
    "TTSLeague2023champions": "TTS League 2023 Champions",
    "TTSLeagueS3": "TTS League Season 3",
    "TTSLeagueS7topCut": "TTS League Season 7 Top Cut",
    "UnlandCup25": "Unland Cup 2025",
}

# Season date-range filters for match data filtering
# These appear in event filter dropdowns alongside database events
SEASON_FILTERS = [
    {
        "id": "season_gothic_1",
        "name": "Gothic Season 1",
        "start_date": "2026-01-03",
        "end_date": "2026-02-03",
    },
]
