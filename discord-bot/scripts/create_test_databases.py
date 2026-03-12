"""
Script to create and populate test databases for local development.

Run this script to create fresh test databases with sample data:
    python scripts/create_test_databases.py

This creates databases in discord-bot/test_data/:
    - test_match_records.db
    - test_elo.db
    - test_fart_scores.db
"""

import sqlite3
import os
from datetime import datetime, timedelta
import random

# Create test_data directory
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'test_data')
os.makedirs(TEST_DATA_DIR, exist_ok=True)

# Database paths
MATCH_RECORDS_DB = os.path.join(TEST_DATA_DIR, 'test_match_records.db')
ELO_DB = os.path.join(TEST_DATA_DIR, 'test_elo.db')
FART_DB = os.path.join(TEST_DATA_DIR, 'test_fart_scores.db')

# Sample data
SAMPLE_PLAYERS = [
    ("123456789", "TestPlayer1", "https://cdn.discordapp.com/avatars/123/abc.png"),
    ("123456790", "TestPlayer2", "https://cdn.discordapp.com/avatars/124/def.png"),
    ("123456791", "TestPlayer3", "https://cdn.discordapp.com/avatars/125/ghi.png"),
    ("123456792", "TestPlayer4", "https://cdn.discordapp.com/avatars/126/jkl.png"),
    ("123456793", "TestPlayer5", "https://cdn.discordapp.com/avatars/127/mno.png"),
]

SAMPLE_DECKS = [
    "https://curiosa.io/decks/123-fire-aggro",
    "https://curiosa.io/decks/456-water-control",
    "https://curiosa.io/decks/789-earth-midrange",
    "https://curiosa.io/decks/012-wind-combo",
]


def create_match_records_db():
    """Create and populate test match records database."""
    print(f"Creating {MATCH_RECORDS_DB}...")

    # Remove old database
    if os.path.exists(MATCH_RECORDS_DB):
        os.remove(MATCH_RECORDS_DB)

    conn = sqlite3.connect(MATCH_RECORDS_DB)
    cursor = conn.cursor()

    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            winner_id TEXT NOT NULL,
            loser_id TEXT NOT NULL,
            winner_username TEXT NOT NULL,
            loser_username TEXT NOT NULL,
            winner_deck TEXT,
            loser_deck TEXT,
            winner_elo_change REAL,
            loser_elo_change REAL,
            winner_new_elo REAL,
            loser_new_elo REAL,
            match_format TEXT DEFAULT 'Casual',
            match_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            game_type TEXT DEFAULT 'Standard',
            event_id INTEGER
        )
    ''')

    # Insert sample matches
    base_date = datetime.now() - timedelta(days=30)
    for i in range(20):
        winner = random.choice(SAMPLE_PLAYERS)
        loser = random.choice([p for p in SAMPLE_PLAYERS if p != winner])
        match_date = base_date + timedelta(days=random.randint(0, 30))

        # Simulate ELO changes
        winner_elo_change = round(random.uniform(10, 30), 2)
        loser_elo_change = -winner_elo_change
        winner_new_elo = round(1000 + random.uniform(-100, 300), 2)
        loser_new_elo = round(1000 + random.uniform(-100, 300), 2)

        cursor.execute('''
            INSERT INTO matches (
                winner_id, loser_id, winner_username, loser_username,
                winner_deck, loser_deck,
                winner_elo_change, loser_elo_change,
                winner_new_elo, loser_new_elo,
                match_format, match_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            winner[0], loser[0], winner[1], loser[1],
            random.choice(SAMPLE_DECKS), random.choice(SAMPLE_DECKS),
            winner_elo_change, loser_elo_change,
            winner_new_elo, loser_new_elo,
            'Casual', match_date
        ))

    conn.commit()
    conn.close()
    print(f"  ✓ Created with {cursor.rowcount} sample matches")


def create_elo_db():
    """Create and populate test ELO database."""
    print(f"Creating {ELO_DB}...")

    # Remove old database
    if os.path.exists(ELO_DB):
        os.remove(ELO_DB)

    conn = sqlite3.connect(ELO_DB)
    cursor = conn.cursor()

    # Create players table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            elo REAL DEFAULT 1000,
            avatar_url TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert sample players with varied ELO
    for i, (user_id, username, avatar_url) in enumerate(SAMPLE_PLAYERS):
        elo = round(1000 + random.uniform(-200, 400), 2)
        wins = random.randint(0, 20)
        losses = random.randint(0, 20)

        cursor.execute('''
            INSERT INTO players (user_id, username, elo, avatar_url, wins, losses)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, elo, avatar_url, wins, losses))

    # Create events table (for tournament tracking)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            event_date DATE NOT NULL,
            winner_id TEXT,
            FOREIGN KEY (winner_id) REFERENCES players(user_id)
        )
    ''')

    # Insert sample event
    cursor.execute('''
        INSERT INTO events (event_name, event_date, winner_id)
        VALUES (?, ?, ?)
    ''', ("Test Tournament #1", datetime.now().date(), SAMPLE_PLAYERS[0][0]))

    conn.commit()
    conn.close()
    print(f"  ✓ Created with {len(SAMPLE_PLAYERS)} sample players and 1 event")


def create_fart_db():
    """Create and populate test fart game database."""
    print(f"Creating {FART_DB}...")

    # Remove old database
    if os.path.exists(FART_DB):
        os.remove(FART_DB)

    conn = sqlite3.connect(FART_DB)
    cursor = conn.cursor()

    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fart_scores (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            last_fart TIMESTAMP
        )
    ''')

    # Insert sample scores
    for user_id, username, _ in SAMPLE_PLAYERS[:3]:  # Only first 3 players
        score = random.randint(0, 100)
        last_fart = datetime.now() - timedelta(hours=random.randint(1, 72))

        cursor.execute('''
            INSERT INTO fart_scores (user_id, username, score, last_fart)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, score, last_fart))

    conn.commit()
    conn.close()
    print(f"  ✓ Created with {cursor.rowcount} sample fart scores")


def verify_databases():
    """Verify databases were created successfully."""
    print("\nVerifying databases...")

    errors = []

    # Check match records
    try:
        conn = sqlite3.connect(MATCH_RECORDS_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM matches")
        count = cursor.fetchone()[0]
        print(f"  ✓ Match records: {count} matches")
        conn.close()
    except Exception as e:
        errors.append(f"Match records error: {e}")

    # Check ELO
    try:
        conn = sqlite3.connect(ELO_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM players")
        count = cursor.fetchone()[0]
        print(f"  ✓ ELO database: {count} players")
        conn.close()
    except Exception as e:
        errors.append(f"ELO database error: {e}")

    # Check fart scores
    try:
        conn = sqlite3.connect(FART_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM fart_scores")
        count = cursor.fetchone()[0]
        print(f"  ✓ Fart database: {count} scores")
        conn.close()
    except Exception as e:
        errors.append(f"Fart database error: {e}")

    if errors:
        print("\n⚠️  Errors encountered:")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("\n✅ All test databases created successfully!")
        return True


if __name__ == "__main__":
    print("Creating test databases...\n")

    create_match_records_db()
    create_elo_db()
    create_fart_db()

    success = verify_databases()

    if success:
        print(f"\nTest databases ready at: {TEST_DATA_DIR}")
        print("\nNext steps:")
        print("1. Copy config.example.py to config.py")
        print("2. Update config.py to use test database paths:")
        print(f"   MATCH_RECORDS_DB = '{MATCH_RECORDS_DB}'")
        print(f"   ELO_DB = '{ELO_DB}'")
        print(f"   FART_DB = '{FART_DB}'")
        print("3. Use a test bot token in .env or config.py")
        print("4. Run the bot: python main.py")
    else:
        print("\n❌ Failed to create test databases")
        exit(1)
