# LFG System Tests

Comprehensive test suite for the Looking For Game (LFG) queue and matching system.

## Running Tests

### All tests
```bash
pytest tests/ -v
```

### Specific test file
```bash
pytest tests/test_lfg_queue.py -v
pytest tests/test_lfg_helpers.py -v
pytest tests/test_lfg_flow.py -v
pytest tests/test_match_reports.py -v
```

### Specific test class
```bash
pytest tests/test_lfg_queue.py::TestLFGQueueBasics -v
```

### With coverage
```bash
pytest tests/ --cov=cogs.lfg --cov=utils --cov-report=html
```

## Test Files

### conftest.py
Shared pytest fixtures:
- `mock_user`, `mock_user_2` - Mock Discord Users
- `mock_guild`, `mock_channel` - Mock Discord objects
- `mock_interaction`, `mock_bot`, `mock_ctx` - Mock Discord contexts
- `setup_test_databases` - Auto database setup/cleanup

### test_lfg_queue.py (25+ tests)
Queue operations and matching:
- TestLFGQueueBasics - Add/remove users, duplicates, deck URLs
- TestQueueExpiration - Expire entries, validate timeframes (5-240 min)
- TestMatchingLogic - Two-user matching, empty queue handling
- TestConcurrentAccess - Thread-safe operations with locks
- TestQueueState - Pending reports, processed matches tracking

### test_lfg_helpers.py (23+ tests)
URL scrubbing utilities:
- TestURLScrubbing - Scrub HTTP/HTTPS URLs, preserve formatting
- TestURLPattern - URL regex patterns
- TestScrubIntegration - Integration with Discord messages
- TestHelperEdgeCases - Long messages, unicode, special chars

### test_lfg_flow.py (20+ tests)
End-to-end flows:
- TestLFGMatchFlow - Queue → Match → Report
- TestQueueCleanupFlow - Expiration and cleanup
- TestURLHandlingInFlow - URL preservation and scrubbing
- TestReportingFlow - Reporter selection, confirmation
- TestStateReset - State isolation between tests

### test_match_reports.py
Match reporting database tests (existing):
- Winner/loser reports
- Database schema validation
- ELO updates

## Summary

Total tests: 70+

Coverage areas:
- Queue operations (15 tests)
- Matching logic (4 tests)
- URL handling (23 tests)
- Integration flows (20 tests)
- State management (12 tests)
- Database operations (existing)

## Running

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=cogs.lfg --cov=utils

# Stop on first failure
pytest tests/ -x
```
