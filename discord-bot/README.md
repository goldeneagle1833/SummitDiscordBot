# Summit Discord Bot - Refactored Structure

## Project Structure

```
summit-bot/
├── main.py                      # Bot entry point
├── config.py                    # Configuration settings
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables (not in git)
│
├── cogs/                        # Command modules (Cogs)
│   ├── __init__.py
│   ├── lfg.py                   # LFG matchmaking system
│   ├── elo.py                   # ELO ranking and player stats
│   ├── fun.py                   # Fun commands (fart system)
│   └── utility.py               # Utility commands (help, deck check)
│
└── utils/                       # Utility functions
    ├── __init__.py
    ├── database.py              # Database operations
    ├── deck_checker.py          # Curiosa deck scraping/checking
    └── constants.py             # Constant values (nicknames, etc.)
```

## File Descriptions

### Main Files

- **`main.py`**: Entry point for the bot. Sets up logging, loads cogs, and handles the `on_ready` and `on_member_join` events.
- **`config.py`**: Centralized configuration for IDs, tokens, and settings.

### Cogs (Command Modules)

#### `cogs/lfg.py`

- LFG queue management
- Match pairing system
- Match reporting modals and buttons
- Commands: `!lfg`, `!checklfg`, `!cancel`

#### `cogs/elo.py`

- ELO ranking system
- Player statistics tracking
- Match history and replay
- Commands: `!rank`, `!leaderboard`, `!mystats`, `!replay`

#### `cogs/fun.py`

- Fart scoring system
- Daily fart/attack mechanics
- Leader role management
- OpenAI integration for responses
- Commands: `!fart`, `!fartrank`, `!fartleaderboard`, `!attackfart`

#### `cogs/utility.py`

- General utility commands
- Deck checking functionality
- Help/command listing
- Commands: `!command`, `!deckcheck`, `!match_report`

### Utils (Helper Functions)

#### `utils/database.py`

- Database creation and management
- ELO calculation and updates
- Match result recording (winner/loser reports)
- Functions: `create_db()`, `update_elo()`, `update_elo_db()`, `winner_report()`, `losser_report()`

#### `utils/deck_checker.py`

- Curiosa API integration
- Deck data scraping and storage
- Card searching and filtering
- Functions: `get_deck_id()`, `scrape_Curosa()`, `search_deck()`, `find_card()`, etc.

#### `utils/constants.py`

- Sorcery nicknames list
- Other constant values used across the bot

## Setup Instructions

1. **Install Dependencies**

   ```bash
   pip install discord.py python-dotenv openai requests
   ```

2. **Create `.env` File**

   ```
   TOKEN=your_discord_bot_token
   OPENAI_API_KEY=your_openai_api_key
   ```

3. **Update Configuration**

   - Edit `config.py` with your server/channel/role IDs

4. **Create Required Directories**

   ```bash
   mkdir cogs utils
   touch cogs/__init__.py utils/__init__.py
   ```

5. **Run the Bot**
   ```bash
   python main.py
   ```

## Database Files

The bot creates the following SQLite databases:

- `match_records.db` - Match history and results
- `elo.db` - Player ELO ratings and standings
- `fart_scores.db` - Fart game scores and timestamps

## Migration from Original File

If you're migrating from the original single-file structure:

1. Copy all the new files into your project directory
2. Ensure your `.env` file has the necessary tokens
3. Update IDs in `config.py` to match your server
4. The bot will automatically create databases on first run
5. All existing database files will continue to work

## Benefits of This Structure

- **Maintainability**: Each module has a clear, single responsibility
- **Scalability**: Easy to add new cogs or utilities
- **Debugging**: Isolated modules make issues easier to track
- **Collaboration**: Multiple developers can work on different cogs
- **Testing**: Individual modules can be tested in isolation
- **Code Reuse**: Utility functions are centralized and reusable

## Adding New Commands

To add a new command to an existing cog:

```python
@commands.command()
async def my_command(self, ctx):
    """Command description."""
    # Your code here
    await ctx.send("Response")
```

To create a new cog:

1. Create a new file in `cogs/` (e.g., `cogs/my_cog.py`)
2. Define a class inheriting from `commands.Cog`
3. Add commands using the `@commands.command()` decorator
4. Include a `setup()` function at the bottom
5. Load it in `main.py` in the `setup_cogs()` function

## Notes

- All cogs use the same logger instance
- Database connections are opened and closed within each function
- The LFG queue is stored in memory (resets on bot restart)
- OpenAI integration requires a valid API key in `.env`
