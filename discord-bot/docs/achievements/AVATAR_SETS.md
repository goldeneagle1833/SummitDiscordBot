# Avatar Set Achievements

## Overview

The bot tracks achievements for playing games with avatars from different sets. These achievements are earned by using avatars from specific card sets in your deck.

## Available Avatar Achievements

### 🅰️ Alpha Initiate

**Description:** Play a game using an Alpha set avatar  
**Database Column:** `alpha_avatar`  
**Check Function:** `check_alpha_avatar()`

#### Alpha Set Avatars

Avatars from the Alpha set were released on **April 19, 2023**. These include:

- Avatar of Air
- Avatar of Earth
- Avatar of Fire
- Avatar of Water
- Avatar of Wisdom
- Avatar of Strength
- Avatar of Valor
- Avatar of Cunning
- Avatar of Shadows
- Avatar of Light

### 🅱️ Beta Warrior

**Description:** Play a game using a Beta set avatar  
**Database Column:** `beta_avatar`  
**Check Function:** `check_beta_avatar()`

#### Beta Set Avatars

Avatars from the Beta set were released on **June 15, 2023** (approximately).

### ⚔️ Arthurian Legends Avatars

While not currently tracked as achievements, the system also supports detection of Arthurian Legends avatars, which were released on **October 4, 2024**. These include:

- Druid
- Templar
- Witch
- And others from the Arthurian Legends set

## How It Works

### Deck Data Structure

When a match is reported with deck data, the avatar information is stored in JSON format:

```json
{
  "avatar": [
    {
      "name": "Avatar of Air",
      "rarity": "Elite",
      "type": "Avatar",
      "sets": [
        {
          "name": "Alpha",
          "releasedAt": "2023-04-19T00:00:00.000Z"
        }
      ]
    }
  ],
  "spellbook": [...],
  "atlas": [...],
  "sideboard": [...]
}
```

### Detection Logic

The `check_avatar_set_usage()` function:

1. **Queries Database:** Retrieves all games played by the user that have deck data
2. **Parses JSON:** Extracts the avatar card from the deck data
3. **Checks Set:** Looks for the set name in two locations:
   - `avatar[0].set_name` - Simple format
   - `avatar[0].sets[].name` - Array format (matches All_Cards_Array.json structure)
4. **Returns Result:** Returns `True` if a match is found, `False` otherwise

### Code Example

```python
async def check_avatar_set_usage(discord_id: str, set_name: str) -> bool:
    """Check if user has played a game with an avatar from a specific set."""
    conn = sqlite3.connect("match_records.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT json_deck_data FROM match_records
        WHERE reporter_id = ? AND json_deck_data IS NOT NULL
        UNION ALL
        SELECT json_deck_data FROM solo_match_reports
        WHERE reporter_id = ? AND json_deck_data IS NOT NULL
    """, (discord_id, discord_id))

    rows = cur.fetchall()
    conn.close()

    for row in rows:
        try:
            deck_data = json.loads(row[0])
            avatar = deck_data.get("avatar", [])

            if avatar and len(avatar) > 0:
                avatar_card = avatar[0]

                # Check set_name field
                if "set_name" in avatar_card:
                    if avatar_card.get("set_name", "").lower() == set_name.lower():
                        return True

                # Check sets array
                if "sets" in avatar_card:
                    for card_set in avatar_card.get("sets", []):
                        if isinstance(card_set, dict):
                            if card_set.get("name", "").lower() == set_name.lower():
                                return True

        except (json.JSONDecodeError, KeyError, TypeError, IndexError):
            continue

    return False
```

## Adding New Avatar Set Achievements

To add a new avatar set achievement (e.g., for Arthurian Legends):

### 1. Add Database Column

In `utils/achievements.py`, update `create_profiles_db()`:

```python
cur.execute("""CREATE TABLE IF NOT EXISTS profiles
               (discord_id TEXT PRIMARY KEY,
                username TEXT,
                ...
                arthurian_avatar BOOLEAN DEFAULT 0,
                ...
               )""")

# Add migration code
try:
    cur.execute("SELECT arthurian_avatar FROM profiles LIMIT 1")
except sqlite3.OperationalError:
    logger.info("Adding arthurian_avatar column to profiles table...")
    cur.execute("ALTER TABLE profiles ADD COLUMN arthurian_avatar BOOLEAN DEFAULT 0")
    logger.info("Successfully added arthurian_avatar column")
```

### 2. Create Check Function

```python
async def check_arthurian_avatar(discord_id: str) -> bool:
    """Check if user has played with an Arthurian Legends set avatar."""
    return await check_avatar_set_usage(discord_id, "Arthurian Legends")
```

### 3. Add to ACHIEVEMENTS Registry

```python
ACHIEVEMENTS = {
    ...
    "arthurian_avatar": {
        "name": "⚔️ Arthurian Legend",
        "description": "Play a game using an Arthurian Legends set avatar",
        "emoji": "⚔️",
        "check_func": check_arthurian_avatar
    },
    ...
}
```

### 4. Update Total Achievement Count

Update any displays showing "X/9 achievements" to reflect the new total (e.g., "X/10 achievements").

## Testing

Use the test file `tests/test_avatar_sets.py` to verify avatar detection:

```bash
python tests/test_avatar_sets.py
```

This will test:

- Alpha set avatar detection
- Beta set avatar detection
- Arthurian Legends avatar detection
- Different deck data formats

## Data Source

Avatar set information comes from `data/All_Cards_Array.json`, which contains the complete card database with set information for all cards including avatars.

## Troubleshooting

### Achievement Not Unlocking

1. **Check Deck Data:** Ensure the match was reported with `json_deck_data` populated
2. **Verify Format:** Check that the avatar data includes either `set_name` or `sets` array
3. **Case Sensitivity:** The system uses case-insensitive matching (`.lower()`)
4. **Database Query:** Verify the user's games are in `match_records` or `solo_match_reports`

### Manual Testing

Run the admin command to force an achievement check:

```
!checkachievements @user
```

This will re-evaluate all achievements for the specified user and announce any newly earned ones.
