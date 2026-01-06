# Tests Directory

This directory contains test scripts for the Summit Discord Bot.

## Test Files

### `test_match_reports.py`

Tests for the match reporting system. These tests run in the GitHub Actions pipeline and will **block deployment** if they fail.

**What it tests:**

- `winner_report` function - correct parameters and database insertion
- `losser_report` function - correct parameters and database insertion
- `solo_match_report` function - correct parameters and database insertion
- Database schema integrity
- Function signatures (parameter count validation)

**Running locally:**

```bash
cd discord-bot
pip install pytest pytest-asyncio
python -m pytest tests/test_match_reports.py -v
```

## CI/CD Integration

Tests run automatically on every push to `main` branch via GitHub Actions.

- ✅ Tests pass → Deployment proceeds
- ❌ Tests fail → Deployment blocked

## Adding New Tests

1. Create a new test file in this directory (e.g., `test_feature.py`)
2. Use pytest conventions (`test_` prefix for functions)
3. Add the test file to the GitHub Actions workflow if needed

## Notes

- Tests use mock data and don't require a live bot connection
- Database connections use temporary test databases
- Tests are standalone and can be run independently
- No Discord API credentials needed for these tests
