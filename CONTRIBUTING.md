# Contributing to Summit Discord Bot

Thank you for your interest in contributing! This guide will help you set up your environment and submit changes.

## 🚀 Quick Start

1. **Fork the repository**
   - Click "Fork" on GitHub to create your own copy

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/SummitDiscordBot.git
   cd SummitDiscordBot
   ```

3. **Set up your test environment**
   ```bash
   cd discord-bot
   pip install -r requirements.txt
   python scripts/create_test_databases.py
   cp config.example.py config.py
   ```

4. **Create a test Discord bot**
   - Go to https://discord.com/developers/applications
   - Create a new application
   - Go to "Bot" tab → Create bot token
   - Enable these intents: `message_content`, `members`, `presences`
   - Save token to `discord-bot/.env`:
     ```
     TOKEN=your_test_bot_token_here
     OPENAI_API_KEY=your_openai_key_here  # Optional for testing
     ```

5. **Create a test Discord server**
   - Create a new server in Discord
   - Invite your test bot with this URL (replace CLIENT_ID):
     ```
     https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=8&scope=bot%20applications.commands
     ```
   - Get channel IDs (enable Developer Mode → right-click channels → Copy ID)
   - Update `config.py` with your test server channel/role IDs

6. **Make your changes**
   ```bash
   git checkout -b feature/my-awesome-feature
   # Make your changes
   pytest tests/ -v  # Run tests
   ```

7. **Submit a pull request**
   ```bash
   git add .
   git commit -m "Add feature: description of changes"
   git push origin feature/my-awesome-feature
   ```
   - Open a PR on GitHub from your fork to the main repository

## 📋 Contribution Guidelines

### What We Accept
- ✅ Bug fixes
- ✅ New features (discuss in an issue first)
- ✅ Performance improvements
- ✅ Documentation improvements
- ✅ Test coverage improvements
- ✅ Code refactoring (with tests)

### What We Don't Accept
- ❌ Breaking changes without discussion
- ❌ Code without tests
- ❌ Commits with secrets/API keys
- ❌ Changes to production config files

### Code Standards
- Follow existing code style and patterns (see [CLAUDE.md](CLAUDE.md))
- Write tests for new functionality
- Keep PRs focused and small (under 500 lines when possible)
- Update documentation when adding features
- No hardcoded values - use `config.py`

### Before Submitting
- [ ] Tests pass: `pytest tests/ -v`
- [ ] No syntax errors: `python -m py_compile cogs/**/*.py`
- [ ] Tested manually in your test Discord server
- [ ] Added tests for new features
- [ ] Updated documentation (CLAUDE.md, README.md)
- [ ] No secrets in code (check `.gitignore`)
- [ ] Descriptive commit messages

## 🧪 Testing

### Running Tests
```bash
cd discord-bot
pytest tests/ -v                    # Run all tests
pytest tests/test_lfg_queue.py -v  # Run specific test file
pytest -k "test_name" -v            # Run specific test
```

### Writing Tests
- Put tests in `discord-bot/tests/`
- Use fixtures from `conftest.py`
- Follow existing test patterns
- Test both success and error cases

Example:
```python
import pytest

@pytest.mark.asyncio
async def test_my_feature(bot, ctx, mock_user):
    """Test description."""
    # Arrange
    # Act
    # Assert
```

### Test Databases
- Use test databases in `test_data/`
- Reset with: `python scripts/create_test_databases.py`
- Never connect to production databases

## 🏗️ Project Structure

```
SummitDiscordBot/
├── discord-bot/          # Main Discord bot
│   ├── cogs/            # Command modules
│   ├── utils/           # Utilities (database, text, etc.)
│   ├── repositories/    # Data access layer
│   ├── services/        # Business logic
│   ├── tests/           # Test suite
│   ├── scripts/         # Helper scripts
│   ├── config.py        # Configuration (gitignored)
│   └── main.py          # Entry point
├── web-app/             # Flask web application
├── CLAUDE.md            # Project documentation
└── TESTING.md           # Testing guide
```

## 🔄 PR Process

1. **Open PR** - GitHub Actions automatically runs tests
2. **Review** - Maintainer reviews code
3. **Iterate** - Address feedback if needed
4. **Merge** - Maintainer merges to main
5. **Deploy** - Auto-deploys to production

### PR Checklist
When you open a PR, ensure:
- [ ] Clear title describing the change
- [ ] Description explaining what and why
- [ ] Tests pass (GitHub Actions shows ✅)
- [ ] No merge conflicts
- [ ] Requested reviewers assigned

## 💡 Getting Help

- **Documentation**: Read [CLAUDE.md](CLAUDE.md) for architecture details
- **Testing**: See [TESTING.md](TESTING.md) for testing guide
- **Issues**: Open an issue to discuss before starting big changes
- **Questions**: Ask in GitHub Discussions or Discord

## 🐛 Reporting Bugs

When reporting bugs, include:
1. **Description**: What happened vs. what should happen
2. **Steps to reproduce**: Exact commands/actions to trigger the bug
3. **Environment**: Bot version, Discord.py version, Python version
4. **Logs**: Relevant error messages or logs
5. **Screenshots**: If applicable

## 🎯 Feature Requests

When requesting features:
1. **Use case**: Why is this needed?
2. **Proposed solution**: How should it work?
3. **Alternatives**: Other approaches you considered
4. **Examples**: Other bots/apps that do this well

## 📜 Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help others learn and grow

## 🏆 Recognition

Contributors are recognized in:
- PR merge commits
- Release notes
- GitHub contributor graph

Thank you for contributing! 🎉
