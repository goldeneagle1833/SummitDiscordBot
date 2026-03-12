"""
Configuration settings for the bot - EXAMPLE FILE

Copy this file to config.py and fill in your own values:
    cp config.example.py config.py

For local testing, use test databases and a test bot token.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from discord-bot directory (where this config file is)
_config_dir = Path(__file__).parent
load_dotenv(_config_dir / ".env")

# Bot Configuration
# Create a test bot at https://discord.com/developers/applications
TOKEN = os.getenv("TOKEN")  # Put your test bot token in .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Optional for testing

# Database Paths
# For testing, use test databases (create with: python scripts/create_test_databases.py)
MATCH_RECORDS_DB = "test_data/test_match_records.db"  # Change for production
ELO_DB = "test_data/test_elo.db"  # Change for production
FART_DB = "test_data/test_fart_scores.db"  # Change for production

# Channel IDs
# Replace these with your test Discord server channel IDs
# You can get IDs by enabling Developer Mode in Discord and right-clicking channels
FART_CHANNEL_ID = 000000000000000000  # Replace with your test channel ID
LFG_CHANNEL_ID = 000000000000000000  # Replace with your test channel ID
WELCOME_CHANNEL_ID = 000000000000000000  # Replace with your test channel ID
MILESTONE_CHANNEL_ID = 000000000000000000  # Replace with your test channel ID
LEADERBOARD_CHANNEL_ID = 000000000000000000  # Replace with your test channel ID
DM_DISABLED_CHANNEL_ID = 000000000000000000  # Replace with your test channel ID
DECKLISTS_CHANNEL_ID = 000000000000000000  # Replace with your test channel ID

# User/Role IDs
# Replace these with your Discord user ID and test server role IDs
OWNER_ID = 000000000000000000  # Your Discord user ID
GUILD_ID = 000000000000000000  # Your test server (guild) ID
SUMMIT_GUILD_ID = 000000000000000000  # Same as GUILD_ID for testing
LEADER_ROLE_ID = 000000000000000000  # Create test roles in your test server
DM_DISABLED_ROLE_ID = 000000000000000000
MASTERS_ROLE_IDS = {000000000000000000}  # Set of role IDs
TICKET_HOLDER_ROLE_IDS = {000000000000000000}
MAGE_ROLE_ID = 000000000000000000
BOT_ADMIN_ROLE_ID = 000000000000000000

# LFG Settings
CHALLENGE_TIMEOUT = 180  # seconds
DEFAULT_TIMEFRAME = 30  # minutes

# Summit Discord invite (for multi-server branding)
SUMMIT_DISCORD_INVITE = "https://discord.gg/sorcererssummit"

# File names
DECK_DATA_FILE = "deck_data_test.json"


"""
Configuration for SorceryAI RAG System
"""
# SorceryAI paths - point to the SorceryAI directory
SORCERY_AI_DIR = Path(__file__).parent.parent / "SorceryAI"
KNOWLEDGE_BASE_DIR = SORCERY_AI_DIR / "knowledge_base"
DATA_DIR = SORCERY_AI_DIR / "data"
CHROMA_DB_DIR = DATA_DIR / "chroma_db"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
CHROMA_DB_DIR.mkdir(exist_ok=True)

# OpenAI Configuration (OPENAI_API_KEY is set at top of file from .env)
EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"  # Use cheaper model for testing

# Embedding Configuration
EMBEDDING_DIMENSIONS = 1536  # for text-embedding-3-small
CHUNK_SIZE = 750  # tokens per chunk
CHUNK_OVERLAP = 100  # token overlap between chunks

# Retrieval Configuration
TOP_K_RESULTS = 10  # Number of chunks to retrieve
SIMILARITY_THRESHOLD = 0.7  # Minimum similarity score

# Generation Configuration
MAX_CONTEXT_LENGTH = 4000  # Max tokens for context
MAX_RESPONSE_LENGTH = 500  # Max tokens for response
TEMPERATURE = 0.2  # Lower = more consistent responses

# ChromaDB Configuration
COLLECTION_NAME = "sorcery_rules"
DISTANCE_METRIC = "cosine"  # or "l2", "ip"
