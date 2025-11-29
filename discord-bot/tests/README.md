# Tests Directory

This directory contains test scripts for the Summit Discord Bot.

## Test Files

### `test_achievements.py`

Comprehensive test suite for the achievement system.

**Purpose:**

- Tests all achievement check functions
- Validates database operations
- Ensures achievement logic works correctly

**Usage:**

```bash
python tests/test_achievements.py
```

**What it tests:**

- Win-based achievements (5, 10, 25 games)
- Elo-based achievements (1600, 1700, 1800)
- Avatar-based achievements (Alpha, Beta)
- Special achievements (Century Club, First Strike Master, Comeback King, Peasant's Fury)

---

### `test_peasants_fury.py`

Specific test for the Peasant's Fury achievement logic.

**Purpose:**

- Validates deck rarity checking
- Tests card filtering (excludes avatar)
- Demonstrates qualifying vs disqualifying decks

**Usage:**

```bash
python tests/test_peasants_fury.py
```

**What it tests:**

- Deck with Elite/Unique cards (should NOT qualify)
- Deck with only Ordinary/Exceptional cards (should qualify)
- Avatar rarity exclusion (any avatar allowed)
- Card location checking (spellbook, atlas, sideboard)

**Example Output:**

```
============================================================
Testing Peasant's Fury Achievement
============================================================
Deck: Big Fury by Goldeneagle1833
============================================================
Total cards to check (excluding avatar): 10

Card rarities:
  - Root Spider: Exceptional
  - Earthquake: Elite
  - Courtesan Thais: Unique
  ...

❌ DISQUALIFIED - Contains 2 non-Ordinary/Exceptional cards:
  - Earthquake: Elite
  - Courtesan Thais: Unique
```

---

## Running All Tests

To run all tests at once:

```bash
cd discord-bot/tests
python test_achievements.py
python test_peasants_fury.py
```

## Notes

- These tests use mock data and don't require a live bot connection
- Database connections are made to local .db files in the bot directory
- Tests are standalone and can be run independently
- No Discord API credentials needed for these tests
