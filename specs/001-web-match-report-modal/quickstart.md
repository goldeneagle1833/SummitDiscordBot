# Quickstart: Web-Based Match Reporting

**Feature**: 001-web-match-report-modal
**For Developers**: Quick setup and development guide

## Prerequisites

- Python 3.11+
- Flask web app already running (see `web-app/README.md`)
- Discord OAuth configured (DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET)
- SQLite database: `discord-bot/match_records.db`

## Setup (5 minutes)

### 1. Install Dependencies

```bash
cd web-app
pip install APScheduler==3.10.4
# Or add to requirements.txt and run:
pip install -r requirements.txt
```

### 2. Run Database Migration

```bash
cd discord-bot
sqlite3 match_records.db < ../specs/001-web-match-report-modal/migration.sql
# Or use Python:
python -c "
import sqlite3
conn = sqlite3.connect('match_records.db')
conn.execute('ALTER TABLE match_confirmations ADD COLUMN went_first TEXT')
conn.execute('ALTER TABLE match_confirmations ADD COLUMN reminder_sent_at INTEGER')
conn.execute('CREATE INDEX IF NOT EXISTS idx_opponent_pending ON match_confirmations(opponent_discord_id, status, expires_at)')
conn.commit()
conn.close()
print('Migration complete')
"
```

### 3. Start Development Server

```bash
cd web-app
python app.py
# App runs on http://localhost:5000
```

### 4. Test Authentication

1. Navigate to `http://localhost:5000/auth/discord`
2. Log in with Discord
3. Check session: `http://localhost:5000/api/match-report/pending`
   - Should return `{"success": true, "pending_confirmations": [], "count": 0}`

## Development Workflow

### Project Structure

```
web-app/
├── routes/
│   └── api/
│       └── match_reporting.py          # NEW: API endpoints
├── services/
│   └── match_confirmation.py           # Extend: Business logic
├── repositories/
│   └── match_confirmation.py           # Extend: Database access
├── templates/
│   └── pages/
│       └── life_counter.html           # Extend: Add modal forms
└── static/
    ├── css/
    │   └── pages/
    │       └── life_counter.css        # Extend: Modal styles
    └── js/
        └── pages/
            └── life_counter.js         # Extend: Modal interactions

specs/001-web-match-report-modal/
├── spec.md                             # Feature requirements
├── research.md                         # Technical decisions
├── data-model.md                       # Database schema
├── contracts/
│   └── api-endpoints.md                # API documentation
├── plan.md                             # Implementation plan
└── quickstart.md                       # This file
```

### Common Tasks

#### Add a New API Endpoint

1. **Define route** (`routes/api/match_reporting.py`):
   ```python
   @match_reporting_bp.route('/my-endpoint', methods=['POST'])
   def my_endpoint():
       # ... implementation
       return jsonify({"success": True})
   ```

2. **Add business logic** (`services/match_confirmation.py`):
   ```python
   def my_service_method(self, param):
       # ... business logic
       return self.repo.my_data_method(param)
   ```

3. **Add data access** (`repositories/match_confirmation.py`):
   ```python
   def my_data_method(self, param):
       conn = self._get_connection()
       cursor = conn.cursor()
       cursor.execute("SELECT ...")
       rows = cursor.fetchall()
       conn.close()
       return rows
   ```

4. **Test with cURL**:
   ```bash
   curl -X POST 'http://localhost:5000/api/match-report/my-endpoint' \
     -H 'Content-Type: application/json' \
     -H 'Cookie: session=...' \
     -d '{"param": "value"}'
   ```

#### Update Frontend Modal

1. **Edit HTML** (`templates/pages/life_counter.html`):
   ```html
   <div id="match-report-modal" class="modal hidden">
     <div class="modal-content">
       <!-- Add form fields here -->
       <input type="text" id="opponent-search" placeholder="Search opponent...">
       <button id="submit-report-btn">Submit Report</button>
     </div>
   </div>
   ```

2. **Add JavaScript** (`static/js/pages/life_counter.js`):
   ```javascript
   document.getElementById('submit-report-btn').addEventListener('click', async () => {
     const response = await fetch('/api/match-report/submit', {
       method: 'POST',
       headers: {'Content-Type': 'application/json'},
       body: JSON.stringify({...})
     });
     const data = await response.json();
     // Handle response
   });
   ```

3. **Add CSS** (`static/css/pages/life_counter.css`):
   ```css
   .modal {
     display: none;
     position: fixed;
     top: 0; left: 0;
     width: 100%; height: 100%;
     background: rgba(0,0,0,0.8);
   }
   .modal:not(.hidden) {
     display: flex;
   }
   ```

#### Run Background Jobs Manually

```python
# In Python console or script:
from services.match_confirmation import MatchConfirmationService

service = MatchConfirmationService()

# Test 24hr reminder job
expired_needing_reminder = service.send_pending_reminders()
print(f"Sent {expired_needing_reminder} reminders")

# Test 48hr expiration job
expired_count = service.expire_old_reports()
print(f"Expired {expired_count} reports")
```

## Testing

### Unit Tests (pytest)

```bash
cd web-app
pytest tests/test_match_confirmation_service.py -v
pytest tests/test_match_confirmation_repo.py -v
```

### Integration Tests (API)

```bash
pytest tests/integration/test_match_reporting_api.py -v
```

### Manual Testing Flow

1. **Submit Report**:
   ```bash
   curl -X POST 'http://localhost:5000/api/match-report/submit' \
     -H 'Content-Type: application/json' \
     -H 'Cookie: session=YOUR_SESSION' \
     -d '{
       "opponent_user_id": "123456789",
       "result": "won",
       "went_first": "submitter",
       "submitter_deck_url": "https://curiosa.io/decks/test1",
       "opponent_deck_url": null,
       "final_life_submitter": 20,
       "final_life_opponent": 0
     }'
   ```

2. **Check Pending** (as opponent):
   ```bash
   curl -X GET 'http://localhost:5000/api/match-report/pending' \
     -H 'Cookie: session=OPPONENT_SESSION'
   ```

3. **Confirm Report**:
   ```bash
   curl -X POST 'http://localhost:5000/api/match-report/confirm/1' \
     -H 'Content-Type: application/json' \
     -H 'Cookie: session=OPPONENT_SESSION' \
     -d '{"confirmation_id": 1}'
   ```

4. **Verify Match Created**:
   ```bash
   sqlite3 discord-bot/match_records.db "SELECT * FROM match_records ORDER BY id DESC LIMIT 1;"
   ```

## Debugging

### Common Issues

**Issue**: "Table match_confirmations has no column went_first"
- **Fix**: Run database migration (step 2 in Setup)

**Issue**: "401 Unauthorized" on API calls
- **Fix**: Ensure you're logged in via `/auth/discord` and sending session cookie

**Issue**: "No module named 'apscheduler'"
- **Fix**: `pip install APScheduler==3.10.4`

**Issue**: Modal doesn't open
- **Fix**: Check browser console for JavaScript errors, ensure `.modal.hidden` class toggle is working

### Logging

Enable debug logging:
```python
# In app.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check logs for API calls:
```bash
tail -f web-app.log  # If using file logging
# Or check console output
```

### Database Inspection

```bash
cd discord-bot
sqlite3 match_records.db

# List all tables
.tables

# Check schema
.schema match_confirmations

# Query pending reports
SELECT id, submitter_discord_id, opponent_discord_id, status, created_at, expires_at
FROM match_confirmations
WHERE status = 'pending'
ORDER BY created_at DESC;

# Exit SQLite
.quit
```

## API Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/match-report/search-opponents?q=name` | GET | Search for opponent |
| `/api/match-report/submit` | POST | Submit new report |
| `/api/match-report/pending` | GET | Get pending confirmations |
| `/api/match-report/confirm/{id}` | POST | Confirm opponent's report |
| `/api/match-report/deny/{id}` | POST | Deny opponent's report |

See `contracts/api-endpoints.md` for full API documentation.

## Helpful Commands

```bash
# Run development server with auto-reload
FLASK_ENV=development python app.py

# Run specific test file
pytest tests/test_match_reporting.py::test_submit_report -v

# Format Python code
black web-app/services/match_confirmation.py

# Lint code
flake8 web-app/routes/api/match_reporting.py

# Check database size
du -h discord-bot/match_records.db

# Backup database
cp discord-bot/match_records.db discord-bot/match_records.db.backup

# Reset test database
rm discord-bot/match_records_test.db
sqlite3 discord-bot/match_records_test.db < specs/001-web-match-report-modal/migration.sql
```

## Environment Variables

```bash
# Required for Discord OAuth
export DISCORD_CLIENT_ID="your_client_id"
export DISCORD_CLIENT_SECRET="your_client_secret"
export DISCORD_REDIRECT_URI="http://localhost:5000/auth/discord/callback"

# Optional: Custom database path
export MATCH_RECORDS_DB_PATH="/custom/path/match_records.db"

# Optional: Flask secret key (auto-generated in dev mode)
export SECRET_KEY="your_secret_key_here"
```

## Next Steps

1. ✅ Setup complete? Test authentication and database access
2. → Implement API endpoints (start with `/submit`)
3. → Add frontend modal forms
4. → Write tests
5. → Deploy to production

## Resources

- **Full API Docs**: [contracts/api-endpoints.md](./contracts/api-endpoints.md)
- **Database Schema**: [data-model.md](./data-model.md)
- **Technical Decisions**: [research.md](./research.md)
- **Flask Docs**: https://flask.palletsprojects.com/
- **APScheduler Docs**: https://apscheduler.readthedocs.io/

## Getting Help

- **Spec Questions**: Check [spec.md](./spec.md) for requirements
- **Implementation Questions**: Check [plan.md](./plan.md) for task breakdown
- **API Questions**: Check [contracts/api-endpoints.md](./contracts/api-endpoints.md)
- **Bug Reports**: File issue with reproduction steps + logs

---

**Happy coding!** 🚀
