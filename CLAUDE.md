# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Summit Discord Bot is a community bot for "Sorcery: Contested Realm" card game. It consists of three integrated systems:

- **discord-bot/** - Python Discord bot (discord.py 2.3+) for matchmaking, ELO ranking, and community features
- **web-app/** - Flask web application for leaderboards, stats, deck viewing, and API
- **SorceryAI/** - RAG-based rules assistant using ChromaDB and OpenAI

## Common Commands

### Discord Bot
```bash
pip install -r discord-bot/requirements.txt
python discord-bot/main.py

# Run tests
pytest discord-bot/tests/
```

### Web Application
```bash
pip install -r web-app/requirements.txt
python web-app/app.py                    # Development
gunicorn -c web-app/gunicorn_config.py   # Production
```

### SorceryAI
```bash
pip install -r SorceryAI/requirements.txt
python SorceryAI/scripts/index_knowledge_base.py  # Re-index knowledge base
python SorceryAI/scripts/test_queries.py          # Test RAG system
pytest SorceryAI/tests/
```

## Architecture

### Discord Bot Cog System

Commands are organized into Cogs (modular command handlers) in `discord-bot/cogs/`:
- `lfg.py` - Looking For Game queue and matchmaking (largest cog)
- `elo.py` - ELO ranking, leaderboards, stats
- `fun.py` - Fart game with OpenAI responses
- `shop.py` - In-game shop and purchases
- `utility.py` - Help, deck checking
- `rules_assistant.py` - SorceryAI integration
- `anti_spam.py` - Spam protection system
- `streaming.py` - Streaming detection and announcements
- `purchase_tracking.py` - Discord monetization/purchase tracking
- `slash_commands.py` - Delegates slash commands to existing cog functions (DRY pattern)

Utilities in `discord-bot/utils/`:
- `database.py` - SQLite database operations (connections opened/closed per function)
- `deck_checker.py` - Curiosa API integration for deck/card data
- `constants.py` - Shared constants and configuration values

### Slash Command Delegation Pattern

Slash commands don't duplicate logic. They:
1. Defer the interaction (prevent timeout)
2. Get the target cog via `bot.get_cog("CogName")`
3. Create context from interaction
4. Call the existing prefix command function

This maintains a single source of truth for command logic.

### Web Application Architecture

The web app uses a layered architecture:

**Routes** (`web-app/routes/`):
- `pages.py` - Page routes (HTML views)
- `auth.py` - Authentication routes (Discord OAuth)
- `api/` - REST API endpoints: `avatars.py`, `cards.py`, `games.py`, `leaderboard.py`, `matches.py`, `players.py`, `rules.py`, `streamers.py`, `misc.py`

**Services** (`web-app/services/`):
- `curiosa.py` - Curiosa API integration
- `leaderboard.py` - Leaderboard business logic
- `match.py` - Match processing
- `player.py` - Player data
- `youtube.py` - YouTube integration

**Repositories** (`web-app/repositories/`):
- `elo.py` - ELO data access
- `events.py` - Event/tournament data access
- `fart.py` - Fart game data access
- `matches.py` - Match data access

**Frontend**: Jinja2 templates in `web-app/templates/` with static CSS/JS in `web-app/static/`.

### RAG System Flow (SorceryAI)

```
User Query -> Embedding (text-embedding-3-small) -> Vector Search (ChromaDB)
           -> Context Assembly -> LLM Generation (GPT) -> Response with Sources
```

The system auto-initializes on first use - no manual indexing required.

Core modules in `SorceryAI/core/`:
- `embeddings.py` - OpenAI embedding integration
- `generator.py` - LLM response generation
- `retriever.py` - Vector retrieval from ChromaDB
- `vector_store.py` - ChromaDB vector store management
- `prompts.py` - System prompts

Knowledge base in `SorceryAI/knowledge_base/`:
- `comprehensive_rules_formatted.md` - Full rulebook
- `quick_start_rules.md` - Quick start guide
- `faq.md` - FAQ
- Card rulings by type: `artifact_cards.md`, `aura_cards.md`, `avatar_cards.md`, `magic_cards.md`, `minion_cards.md`, `site_cards.md`

Data conversion scripts in `SorceryAI/scripts/` convert raw data (CSV, JSON, DOCX) into markdown for indexing.

## Key Configuration

- `discord-bot/config.py` - Centralized bot config (gitignored, contains secrets): API keys, channel/guild/role IDs, SorceryAI paths, RAG parameters
- `web-app/webapp_config.py` - Web app configuration
- `web-app/gunicorn_config.py` - Production WSGI server config
- `.env` - Environment variables (TOKEN, OPENAI_API_KEY) - gitignored

## Database

SQLite databases in `discord-bot/` (gitignored):
- `match_records.db` - Match history with ELO changes and deck data
- `elo.db` - Player ratings
- `fart_scores.db` - Fart game scores

The Discord bot accesses databases directly via `discord-bot/utils/database.py`. The web app uses the repository pattern via `web-app/repositories/`.

## CI/CD and Deployment

**GitHub Actions** (`.github/workflows/`):
- `deploy-bot.yml` - Discord bot deployment
- `deploy-web.yml` - Web app deployment
- `deploy-ai.yml` - SorceryAI deployment

**Production**: systemd services behind Nginx with Cloudflare. Config files in:
- `web-app/systemd/summit-web.service`
- `web-app/nginx/summit-web.conf` / `summit-web-cloudflare.conf`
- See `web-app/DEPLOYMENT.md` and `SorceryAI/DEPLOYMENT.md`

## External Integrations

- **Discord API** - via discord.py (prefix `!` and slash `/` commands)
- **OpenAI API** - GPT models for LLM, text-embedding-3-small for embeddings
- **Curiosa API** - Deck/card data via `utils/deck_checker.py` and `web-app/services/curiosa.py`
- **ChromaDB** - Vector store at `SorceryAI/data/chroma_db/`
- **YouTube API** - Streaming integration via `web-app/services/youtube.py`
- **Discord OAuth** - Web app authentication via `web-app/routes/auth.py`

## Adding New Commands

### Prefix Command (in existing cog)
```python
@commands.command()
async def my_command(self, ctx, param: str):
    await ctx.send(f"Response: {param}")
```

### Slash Command (add to slash_commands.py)
```python
@app_commands.command(name="my_command", description="Description")
async def my_command_slash(self, interaction: discord.Interaction, param: str):
    await interaction.response.defer()
    cog = self.bot.get_cog("TargetCog")
    ctx = await self.bot.get_context(interaction)
    await cog.my_command(ctx, param)
```

### New Cog
1. Create file in `discord-bot/cogs/`
2. Define class inheriting from `commands.Cog`
3. Add `setup()` function at bottom
4. Import and load in `main.py`

## Important Notes

- LFG queue is stored in memory (resets on bot restart)
- Both prefix (`!`) and slash (`/`) commands are supported
- `config.py` and `.env` are gitignored - never commit secrets
- Tournament deck data stored in `web-app/top-8-decks-by-event/` (JSON files per event)
- Bot requires intents: `message_content`, `members`, `presences` (for streaming detection)
- Bot logging goes to `bot.log` (also gitignored)
