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
SORCERY_AI_DIR = BASE_DIR.parent / "SorceryAI"
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

# Curio tracking upload directory
STATIC_DIR = BASE_DIR / "static"
CURIO_UPLOADS_DIR = STATIC_DIR / "uploads" / "curios"
CURIO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

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
ADMINS = [
    "296846802924208130",  # Owner
    "146923845549424640",  # keven
    "128690099432062976",  # ember
    "212395045125357568",  # IRA
    "292113529585008640",  # CJ
    "845209838111031306",  # Kyle
    "275995453957472257",  # Geoffrey
    "google_113075264611538227218",  # Bruce Google
    "219331660833882112",  # vitaninyon
]

# Curio Tracking editors - can add/edit/delete curio entries (no other admin access)
CURIO_EDITORS = [
    # Add Discord/Google IDs of trusted curio editors here
    # Example: "123456789012345678",  # Username
    "961211642216087552",
    "690629397631467671",
    "296846802924208130",
]

# API Key configuration for external integrations
API_KEYS_ENV = os.environ.get("API_KEYS", os.environ.get("API_KEY", ""))
VALID_API_KEYS = [key.strip() for key in API_KEYS_ENV.split(",") if key.strip()]

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
