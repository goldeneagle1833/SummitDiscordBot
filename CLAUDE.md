# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Summit Discord Bot is a community bot for "Sorcery: Contested Realm" card game. It consists of three integrated systems:

- **discord-bot/** - Python Discord bot (discord.py 2.3+) for matchmaking, ELO ranking, and community features
- **web-app/** - Flask web application for leaderboards, stats, and deck viewing
- **SorceryAI/** - RAG-based rules assistant using ChromaDB and OpenAI

## Common Commands

### Discord Bot
```bash
# Install and run
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

Commands are organized into Cogs (modular command handlers):
- `cogs/lfg.py` - Looking For Game queue and matchmaking
- `cogs/elo.py` - ELO ranking, leaderboards, stats
- `cogs/fun.py` - Fart game with OpenAI responses
- `cogs/shop.py` - In-game shop and purchases
- `cogs/utility.py` - Help, deck checking
- `cogs/rules_assistant.py` - SorceryAI integration
- `cogs/slash_commands.py` - Delegates slash commands to existing cog functions (DRY pattern)

### Slash Command Delegation Pattern

Slash commands don't duplicate logic. They:
1. Defer the interaction (prevent timeout)
2. Get the target cog via `bot.get_cog("CogName")`
3. Create context from interaction
4. Call the existing prefix command function

This maintains a single source of truth for command logic.

### RAG System Flow (SorceryAI)

```
User Query → Embedding (text-embedding-3-small) → Vector Search (ChromaDB)
           → Context Assembly → LLM Generation (GPT) → Response with Sources
```

The system auto-initializes on first use - no manual indexing required.

## Key Configuration

All configuration is centralized in `discord-bot/config.py`:
- API keys loaded from `.env` (TOKEN, OPENAI_API_KEY)
- Channel/Guild/Role IDs
- SorceryAI paths and model settings
- RAG parameters (chunk size, similarity threshold, etc.)

## Database

SQLite databases in `discord-bot/`:
- `match_records.db` - Match history with ELO changes and deck data
- `elo.db` - Player ratings
- `fart_scores.db` - Fart game scores

Database operations are in `discord-bot/utils/database.py`. Connections are opened/closed within each function.

## External Integrations

- **Discord API** - via discord.py
- **OpenAI API** - GPT models for LLM, text-embedding-3-small for embeddings
- **Curiosa API** - Deck/card data via `utils/deck_checker.py`
- **ChromaDB** - Vector store at `SorceryAI/data/chroma_db/`

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
4. Import and load in `main.py`'s `setup_cogs()`

## Important Notes

- LFG queue is stored in memory (resets on bot restart)
- Both prefix (`!`) and slash (`/`) commands are supported
- Production deployment uses systemd services - see `web-app/DEPLOYMENT.md` and `SorceryAI/DEPLOYMENT.md`
- Tournament deck data stored in `web-app/top-8-decks-by-event/`
