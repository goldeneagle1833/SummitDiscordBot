# API Key Management Guide

## Current Setup: Multiple Keys in Environment Variable

The current implementation supports multiple API keys stored in the `.env` file.

### Adding a New Key

1. Open `f:\GitHub\SummitDiscordBot\discord-bot\.env`
2. Find the `API_KEYS` line
3. Add your new key to the comma-separated list:

```env
API_KEYS='key1,key2,key3,your_new_key_here'
```

4. Restart the Flask web app for changes to take effect

### Generating a Secure API Key

Use Python to generate a cryptographically secure key:

```python
import secrets
print(secrets.token_urlsafe(32))
```

Or use this online: https://www.uuidgenerator.net/

### Example .env Configuration

```env
API_KEYS='summit_main_key_xyz,tournament_organizer_abc,streamer_overlay_def,mobile_app_ghi'
```

---

## Advanced Option: Database-Backed API Keys

For better management (tracking usage, expiration, permissions), you can implement a database system.

### 1. Create API Keys Table

Create a new file: `discord-bot/utils/api_keys.py`

```python
import sqlite3
import secrets
from datetime import datetime, timedelta

DB_PATH = "api_keys.db"


def create_api_keys_table():
    """Create the API keys table"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            is_active BOOLEAN DEFAULT 1,
            last_used DATETIME,
            usage_count INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def generate_api_key():
    """Generate a new secure API key"""
    return secrets.token_urlsafe(32)


def add_api_key(name, description=None, days_valid=365):
    """Add a new API key"""
    create_api_keys_table()

    api_key = generate_api_key()
    expires_at = datetime.now() + timedelta(days=days_valid) if days_valid else None

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO api_keys (api_key, name, description, expires_at)
            VALUES (?, ?, ?, ?)
        """, (api_key, name, description, expires_at))

        conn.commit()
        key_id = cur.lastrowid
        print(f"✅ API Key created successfully!")
        print(f"   ID: {key_id}")
        print(f"   Name: {name}")
        print(f"   Key: {api_key}")
        print(f"   Expires: {expires_at if expires_at else 'Never'}")
        return api_key
    except sqlite3.IntegrityError:
        print("❌ Error: Key generation collision (very rare). Try again.")
        return None
    finally:
        conn.close()


def validate_api_key(api_key):
    """Check if an API key is valid and active"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT key_id, name, expires_at, is_active
        FROM api_keys
        WHERE api_key = ?
    """, (api_key,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return False, "Invalid API key"

    key_id, name, expires_at, is_active = row

    if not is_active:
        return False, "API key is disabled"

    if expires_at:
        expiry = datetime.fromisoformat(expires_at)
        if datetime.now() > expiry:
            return False, "API key has expired"

    # Update last used and usage count
    update_key_usage(key_id)

    return True, name


def update_key_usage(key_id):
    """Update last_used timestamp and increment usage_count"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        UPDATE api_keys
        SET last_used = CURRENT_TIMESTAMP,
            usage_count = usage_count + 1
        WHERE key_id = ?
    """, (key_id,))

    conn.commit()
    conn.close()


def list_api_keys():
    """List all API keys (without showing the actual keys)"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT key_id, name, description, created_at, expires_at,
               is_active, last_used, usage_count
        FROM api_keys
        ORDER BY created_at DESC
    """)

    keys = cur.fetchall()
    conn.close()

    print("\n📋 API Keys:")
    print("-" * 100)
    for key in keys:
        key_id, name, desc, created, expires, active, last_used, count = key
        status = "✅ Active" if active else "❌ Disabled"
        print(f"ID: {key_id} | {name} | {status} | Uses: {count}")
        if desc:
            print(f"  Description: {desc}")
        print(f"  Created: {created} | Expires: {expires or 'Never'} | Last used: {last_used or 'Never'}")
        print("-" * 100)


def revoke_api_key(key_id):
    """Disable an API key"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("UPDATE api_keys SET is_active = 0 WHERE key_id = ?", (key_id,))

    if cur.rowcount > 0:
        print(f"✅ API Key {key_id} has been revoked")
    else:
        print(f"❌ API Key {key_id} not found")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys

    create_api_keys_table()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python api_keys.py add <name> [description] [days_valid]")
        print("  python api_keys.py list")
        print("  python api_keys.py revoke <key_id>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "add":
        if len(sys.argv) < 3:
            print("❌ Please provide a name for the API key")
            sys.exit(1)

        name = sys.argv[2]
        description = sys.argv[3] if len(sys.argv) > 3 else None
        days_valid = int(sys.argv[4]) if len(sys.argv) > 4 else 365

        add_api_key(name, description, days_valid)

    elif command == "list":
        list_api_keys()

    elif command == "revoke":
        if len(sys.argv) < 3:
            print("❌ Please provide the key ID to revoke")
            sys.exit(1)

        key_id = int(sys.argv[2])
        revoke_api_key(key_id)

    else:
        print(f"❌ Unknown command: {command}")
```

### 2. Update Flask Authentication

Modify `web-app/app.py` to use database validation:

```python
def require_api_key(f):
    """Decorator to require API key authentication for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        provided_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")

        if provided_key and provided_key.startswith("Bearer "):
            provided_key = provided_key[7:]

        # Try database validation first (if implemented)
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent / "discord-bot"))
            from utils.api_keys import validate_api_key

            is_valid, message = validate_api_key(provided_key)
            if is_valid:
                return f(*args, **kwargs)
            else:
                logger.warning(f"API key validation failed: {message}")
        except ImportError:
            # Fall back to environment variable validation
            if not VALID_API_KEYS:
                logger.error("No API keys configured")
                return jsonify({"error": "API authentication not configured"}), 500

            if provided_key and provided_key in VALID_API_KEYS:
                return f(*args, **kwargs)

        logger.warning(f"Unauthorized API access attempt from {request.remote_addr}")
        return jsonify({"error": "Invalid or missing API key"}), 401

    return decorated_function
```

### 3. Managing Keys via Command Line

```bash
# Create a new API key
python discord-bot/utils/api_keys.py add "Tournament Organizer" "For SCG CON 2025" 365

# List all keys
python discord-bot/utils/api_keys.py list

# Revoke a key
python discord-bot/utils/api_keys.py revoke 5
```

---

## Recommended Approach

**For 1-5 users:** Use the simple multi-key environment variable approach (already implemented)

**For 5+ users or production:** Use the database-backed system for:
- Tracking who uses which key
- Monitoring usage patterns
- Expiring/revoking keys
- Better security auditing

---

## Security Best Practices

1. **Never commit API keys to Git**
   - Add `.env` to `.gitignore` (already done)
   - Share keys securely (encrypted chat, password manager, etc.)

2. **Generate strong keys**
   - Use `secrets.token_urlsafe(32)` in Python
   - Minimum 32 characters
   - Use random alphanumeric characters

3. **Rotate keys regularly**
   - Change keys every 6-12 months
   - Immediately revoke compromised keys

4. **Use HTTPS in production**
   - Never send API keys over unencrypted HTTP
   - Use SSL/TLS certificates

5. **Monitor usage**
   - Check logs for suspicious activity
   - Track which keys are being used

6. **Principle of least privilege**
   - Give each integration only the keys it needs
   - Consider creating different endpoint permissions (future enhancement)

---

## Quick Reference

### Current System (Simple Multi-Key)

**Location:** `discord-bot/.env`

**Format:** `API_KEYS='key1,key2,key3'`

**Adding a key:**
1. Edit `.env` file
2. Add to comma-separated list
3. Restart web app

**Example:**
```env
API_KEYS='abc123xyz,def456uvw,ghi789rst'
```

Each key has equal access to all API endpoints.
