# Testing and PR Workflow

## For Contributors: How to Test Your Changes

### 1. Local Testing Setup

#### Create Test Databases
```bash
cd discord-bot
python scripts/create_test_databases.py
```

This creates test databases in `discord-bot/test_data/`:
- `test_match_records.db`
- `test_elo.db`
- `test_fart_scores.db`

#### Run with Test Configuration
```bash
# Copy test config template
cp config.example.py config.py

# Edit config.py to use test database paths:
# MATCH_RECORDS_DB = 'test_data/test_match_records.db'
# ELO_DB = 'test_data/test_elo.db'
# FART_DB = 'test_data/test_fart_scores.db'

# Use a test bot token (create a separate test bot application)
# TOKEN = 'your_test_bot_token_here'
```

#### Run Tests
```bash
cd discord-bot
pytest tests/ -v
```

#### Run the Bot Locally
```bash
python main.py
```

### 2. Testing Your Changes

Before submitting a PR:

1. ✅ **Run all tests**: `pytest tests/ -v`
2. ✅ **Test the commands manually** in your test Discord server
3. ✅ **Check for syntax errors**: `python -m py_compile cogs/**/*.py`
4. ✅ **Verify no secrets committed**: Check `.gitignore` includes `config.py`, `.env`

### 3. Submitting a Pull Request

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Commit with descriptive messages: `git commit -m "Add feature: description"`
5. Push to your fork: `git push origin feature/my-feature`
6. Open a PR on GitHub

**PR Checklist:**
- [ ] Tests pass locally
- [ ] Added tests for new functionality
- [ ] Updated documentation (CLAUDE.md, README.md)
- [ ] No secrets or API keys committed
- [ ] Code follows existing patterns (see CLAUDE.md)

### 4. PR Review Process

1. GitHub Actions will automatically run tests on your PR
2. Maintainer will review code
3. Address any requested changes
4. Once approved, maintainer will merge to main

## For Maintainer: Setting Up Test Environment

### Test Discord Bot Setup

1. **Create a Test Bot Application**
   - Go to https://discord.com/developers/applications
   - Create new application "Summit Bot - Test"
   - Create bot token
   - Enable same intents as production: `message_content`, `members`, `presences`

2. **Create Test Discord Server**
   - Create a new Discord server "Summit - Test"
   - Invite test bot
   - Set up same channels as production (or subset for testing)

3. **Configure Test Environment**
   ```bash
   # On test server/machine
   cd discord-bot
   cp config.example.py config_test.py

   # Edit config_test.py with:
   # - Test guild ID
   # - Test channel IDs
   # - Test database paths (test_data/*.db)
   # - Test OpenAI key (or same key with usage limits)
   ```

4. **Run Test Bot**
   ```bash
   # Use separate systemd service or screen session
   python main.py --config config_test.py
   ```

### Optional: PR-Specific Test Deployments

For advanced setups, you can deploy each PR to a unique test instance:

- Use Docker containers for isolation
- GitHub Actions can build and deploy to test server
- Each PR gets a unique bot instance with isolated databases
- Comment on PR with test bot invite link

See `.github/workflows/pr-test-bot.yml` for automation.

## Database Strategy

### Test Databases vs Production

**Test Databases** (`test_data/*.db`):
- Pre-populated with sample data
- Safe to modify/break
- Reset between test runs
- Used for local development and PRs

**Production Databases** (`*.db`):
- Real user data
- Never committed to git
- Only accessible in production environment
- Backed up regularly

### Creating Test Data

```python
# scripts/create_test_databases.py
import sqlite3

# Creates databases with sample players, matches, etc.
# Run this to reset test data
```

## CI/CD Pipeline

```
PR Opened → GitHub Actions Runs Tests → Manual Review → Approve → Merge → Auto-deploy to Production
```

### Current Workflows

- `.github/workflows/pr-test-bot.yml` - Runs on every PR
- `.github/workflows/deploy-bot.yml` - Runs on merge to main
- `.github/workflows/deploy-web.yml` - Runs on merge to main
- `.github/workflows/deploy-ai.yml` - Runs on merge to main

## Best Practices

### For Contributors
- Always test locally before pushing
- Use test databases, never connect to production
- Write tests for new features
- Keep PRs focused and small

### For Maintainer
- Review PRs promptly
- Test manually in test environment if needed
- Use branch protection to prevent direct pushes to main
- Keep test environment in sync with production structure
