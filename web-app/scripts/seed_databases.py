"""
Create and populate all four SQLite databases for local web app development.

Run from the web-app directory:
    python scripts/seed_databases.py

Creates databases in ../discord-bot/ with correct schemas and sample data:
    - elo.db           (overall_standings, events, event_standings_archive, paper_standings, limited_elo)
    - match_records.db (match_records, match_reports_web, match_confirmations, user_profiles,
                        admin_audit_log, seasons, season_members, season_match_elo,
                        limited_arena_runs, limited_match_records, limited_active_pairings)
    - fart_scores.db   (fart_scores)
    - community.db     (discord_servers, youtube_channels, websites, curio_sets, curio_entries)

Existing databases are NOT overwritten. Delete them first to regenerate.
"""

import sqlite3
import os
import sys
import random
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Resolve paths
SCRIPT_DIR = Path(__file__).parent
WEB_APP_DIR = SCRIPT_DIR.parent
BOT_DIR = WEB_APP_DIR.parent / "discord-bot"

ELO_DB = BOT_DIR / "elo.db"
MATCH_RECORDS_DB = BOT_DIR / "match_records.db"
FART_DB = BOT_DIR / "fart_scores.db"
COMMUNITY_DB = BOT_DIR / "community.db"

# ─── Sample data ─────────────────────────────────────────────────────────────

SAMPLE_PLAYERS = [
    ("100000000000000001", "Pyromancer_Pete"),
    ("100000000000000002", "AquaMage_Amy"),
    ("100000000000000003", "EarthShaker_Ed"),
    ("100000000000000004", "WindWalker_Wendy"),
    ("100000000000000005", "ShadowCaster_Sam"),
    ("100000000000000006", "LightBringer_Lily"),
    ("100000000000000007", "VoidMaster_Vic"),
    ("100000000000000008", "FrostQueen_Fiona"),
    ("100000000000000009", "ThunderLord_Tom"),
    ("100000000000000010", "NatureSage_Nancy"),
]

SAMPLE_DECK_URLS = [
    "https://curiosa.io/decks/fire-aggro-alpha",
    "https://curiosa.io/decks/water-control-beta",
    "https://curiosa.io/decks/earth-midrange-arthurian",
    "https://curiosa.io/decks/wind-combo-gothic",
    "https://curiosa.io/decks/shadow-tempo-alpha",
    "https://curiosa.io/decks/light-ramp-beta",
]

SAMPLE_DECK_JSON = json.dumps({
    "avatar": {"name": "Deckbuilder Avatar", "element": "Fire"},
    "cards": [
        {"name": "Fireball", "count": 4, "type": "Magic"},
        {"name": "Flame Shield", "count": 3, "type": "Aura"},
        {"name": "Fire Elemental", "count": 4, "type": "Minion"},
    ],
})


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ─── elo.db ──────────────────────────────────────────────────────────────────

def create_elo_db():
    """Create elo.db with overall_standings, events, event_standings_archive,
    paper_standings, and limited_elo tables."""

    if ELO_DB.exists():
        print(f"  SKIP  {ELO_DB} already exists")
        return

    print(f"  CREATE  {ELO_DB}")
    conn = sqlite3.connect(str(ELO_DB))
    cur = conn.cursor()

    # ── overall_standings ────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE overall_standings (
            user_id TEXT PRIMARY KEY,
            user_display_name TEXT NOT NULL,
            elo INTEGER NOT NULL DEFAULT 1500,
            event_elo INTEGER DEFAULT 1500,
            paper_elo INTEGER DEFAULT 1500,
            online_elo INTEGER DEFAULT 1500,
            paper_event_elo INTEGER DEFAULT 1500,
            online_event_elo INTEGER DEFAULT 1500
        )
    """)

    for uid, name in SAMPLE_PLAYERS:
        elo = 1500 + random.randint(-200, 400)
        event_elo = 1500 + random.randint(-100, 300)
        paper = 1500 + random.randint(-150, 350)
        online = 1500 + random.randint(-150, 350)
        cur.execute(
            """INSERT INTO overall_standings
               (user_id, user_display_name, elo, event_elo, paper_elo, online_elo,
                paper_event_elo, online_event_elo)
               VALUES (?,?,?,?,?,?,?,?)""",
            (uid, name, elo, event_elo, paper, online, event_elo, event_elo),
        )

    # ── events ───────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            is_active INTEGER NOT NULL DEFAULT 0
        )
    """)

    past_start = (datetime.now() - timedelta(days=90)).isoformat()
    past_end = (datetime.now() - timedelta(days=30)).isoformat()
    active_start = (datetime.now() - timedelta(days=15)).isoformat()

    cur.execute(
        "INSERT INTO events (event_name, start_date, end_date, is_active) VALUES (?,?,?,?)",
        ("Alpha Season", past_start, past_end, 0),
    )
    cur.execute(
        "INSERT INTO events (event_name, start_date, end_date, is_active) VALUES (?,?,?,?)",
        ("Gothic Season 1", active_start, None, 1),
    )

    # ── event_standings_archive ──────────────────────────────────────────
    cur.execute("""
        CREATE TABLE event_standings_archive (
            archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            user_display_name TEXT NOT NULL,
            final_event_elo INTEGER NOT NULL,
            final_rank INTEGER NOT NULL,
            archived_at TEXT NOT NULL
        )
    """)

    for rank, (uid, name) in enumerate(SAMPLE_PLAYERS[:5], start=1):
        cur.execute(
            """INSERT INTO event_standings_archive
               (event_id, user_id, user_display_name, final_event_elo, final_rank, archived_at)
               VALUES (?,?,?,?,?,?)""",
            (1, uid, name, 1500 + (6 - rank) * 50, rank, past_end),
        )

    # ── paper_standings ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE paper_standings (
            user_id TEXT PRIMARY KEY,
            user_display_name TEXT NOT NULL,
            paper_elo INTEGER NOT NULL DEFAULT 1500,
            paper_event_elo INTEGER NOT NULL DEFAULT 1500
        )
    """)

    for uid, name in SAMPLE_PLAYERS[:6]:
        cur.execute(
            "INSERT INTO paper_standings (user_id, user_display_name, paper_elo, paper_event_elo) VALUES (?,?,?,?)",
            (uid, name, 1500 + random.randint(-100, 300), 1500 + random.randint(-50, 200)),
        )

    # ── limited_elo ──────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE limited_elo (
            user_id INTEGER PRIMARY KEY,
            user_display_name TEXT,
            elo INTEGER NOT NULL DEFAULT 1500
        )
    """)

    for uid, name in SAMPLE_PLAYERS[:4]:
        cur.execute(
            "INSERT INTO limited_elo (user_id, user_display_name, elo) VALUES (?,?,?)",
            (int(uid), name, 1500 + random.randint(-100, 200)),
        )

    conn.commit()
    conn.close()
    print(f"          {len(SAMPLE_PLAYERS)} players, 2 events, 5 archived standings")


# ─── match_records.db ────────────────────────────────────────────────────────

def create_match_records_db():
    """Create match_records.db with all tables the web app reads/writes."""

    if MATCH_RECORDS_DB.exists():
        print(f"  SKIP  {MATCH_RECORDS_DB} already exists")
        return

    print(f"  CREATE  {MATCH_RECORDS_DB}")
    conn = sqlite3.connect(str(MATCH_RECORDS_DB))
    cur = conn.cursor()

    # ── match_records (main table read by web app) ───────────────────────
    cur.execute("""
        CREATE TABLE match_records (
            match_id TEXT,
            reporter_id TEXT,
            winner_id TEXT NOT NULL,
            winner_display_name TEXT,
            losser_id TEXT NOT NULL,
            losser_display_name TEXT,
            did_win INTEGER,
            timestamp TEXT,
            first_player TEXT,
            match_time INTEGER,
            curiosa_url TEXT,
            match_comment TEXT,
            json_deck_data TEXT,
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,
            winner_went_first TEXT,
            loser_went_first TEXT,
            curiosa_url_winner TEXT,
            curiosa_url_loser TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT,
            source TEXT DEFAULT 'Discord',
            match_type TEXT DEFAULT 'ranked'
        )
    """)

    # ── match_records_archive ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE match_records_archive (
            match_id TEXT,
            reporter_id TEXT,
            winner_id TEXT NOT NULL,
            winner_display_name TEXT,
            losser_id TEXT NOT NULL,
            losser_display_name TEXT,
            did_win INTEGER,
            timestamp TEXT,
            first_player TEXT,
            match_time INTEGER,
            curiosa_url TEXT,
            match_comment TEXT,
            json_deck_data TEXT,
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,
            winner_went_first TEXT,
            loser_went_first TEXT,
            curiosa_url_winner TEXT,
            curiosa_url_loser TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT,
            source TEXT DEFAULT 'Discord',
            match_type TEXT DEFAULT 'ranked'
        )
    """)

    # Insert sample matches
    base_date = datetime.now(timezone.utc) - timedelta(days=30)
    for i in range(25):
        w_idx = random.randint(0, len(SAMPLE_PLAYERS) - 1)
        l_idx = random.randint(0, len(SAMPLE_PLAYERS) - 2)
        if l_idx >= w_idx:
            l_idx += 1
        winner = SAMPLE_PLAYERS[w_idx]
        loser = SAMPLE_PLAYERS[l_idx]

        ts = (base_date + timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))).isoformat()
        w_elo_change = random.randint(10, 30)
        l_elo_change = -w_elo_change
        went_first = random.choice(["winner", "loser"])
        deck_url_w = random.choice(SAMPLE_DECK_URLS)
        deck_url_l = random.choice(SAMPLE_DECK_URLS)
        source = random.choice(["Discord", "Discord", "Discord", "Web"])

        cur.execute(
            """INSERT INTO match_records
               (reporter_id, winner_id, winner_display_name,
                losser_id, losser_display_name, did_win,
                timestamp, first_player, match_time, match_comment,
                curiosa_url_winner, curiosa_url_loser,
                json_deck_data_winner, json_deck_data_loser,
                winner_elo_change, loser_elo_change,
                winner_went_first, source, match_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                winner[0], winner[0], winner[1],
                loser[0], loser[1], 1,
                ts, went_first, random.randint(300, 1800), None,
                deck_url_w, deck_url_l,
                SAMPLE_DECK_JSON, SAMPLE_DECK_JSON,
                w_elo_change, l_elo_change,
                went_first, source, "ranked",
            ),
        )

    # Insert a few archived matches
    for i in range(5):
        w = SAMPLE_PLAYERS[i]
        l = SAMPLE_PLAYERS[(i + 1) % len(SAMPLE_PLAYERS)]
        ts = (base_date - timedelta(days=60 + i)).isoformat()
        cur.execute(
            """INSERT INTO match_records_archive
               (reporter_id, winner_id, winner_display_name,
                losser_id, losser_display_name, did_win,
                timestamp, first_player, match_time,
                winner_elo_change, loser_elo_change, source, match_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (w[0], w[0], w[1], l[0], l[1], 1, ts, "winner", 600, 20, -20, "Discord", "ranked"),
        )

    # ── match_reports_web ────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE match_reports_web (
            match_id TEXT PRIMARY KEY,
            reporter_id TEXT,
            winner_id TEXT NOT NULL,
            losser_id TEXT NOT NULL,
            winner_display_name TEXT NOT NULL,
            losser_display_name TEXT NOT NULL,
            did_win INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            first_player TEXT,
            match_time INTEGER,
            match_comment TEXT,
            curiosa_url TEXT,
            curiosa_url_winner TEXT,
            curiosa_url_loser TEXT,
            json_deck_data TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT,
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,
            winner_went_first TEXT,
            loser_went_first TEXT,
            source TEXT DEFAULT 'Web',
            match_type TEXT DEFAULT 'ranked',
            season_id INTEGER DEFAULT NULL
        )
    """)
    cur.execute("CREATE INDEX idx_match_reports_web_winner ON match_reports_web(winner_id)")
    cur.execute("CREATE INDEX idx_match_reports_web_loser ON match_reports_web(losser_id)")
    cur.execute("CREATE INDEX idx_match_reports_web_timestamp ON match_reports_web(timestamp DESC)")
    cur.execute("CREATE INDEX idx_match_reports_web_source ON match_reports_web(source)")
    cur.execute("CREATE INDEX idx_match_reports_web_season_id ON match_reports_web(season_id)")

    # ── match_confirmations ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE match_confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submitter_discord_id TEXT NOT NULL,
            opponent_discord_id TEXT NOT NULL,
            winner_discord_id TEXT NOT NULL,
            loser_discord_id TEXT NOT NULL,
            winner_deck_url TEXT,
            loser_deck_url TEXT,
            went_first TEXT CHECK(went_first IN ('submitter', 'opponent')),
            final_life_winner INTEGER NOT NULL,
            final_life_loser INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'confirmed', 'disputed', 'expired', 'auto_confirmed')),
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            reminder_sent_at INTEGER,
            confirmed_at INTEGER,
            dispute_reason TEXT,
            match_type TEXT DEFAULT 'ranked' CHECK(match_type IN ('ranked', 'casual')),
            season_id INTEGER DEFAULT NULL,
            CHECK(submitter_discord_id != opponent_discord_id),
            CHECK(winner_discord_id IN (submitter_discord_id, opponent_discord_id)),
            CHECK(loser_discord_id IN (submitter_discord_id, opponent_discord_id)),
            CHECK(winner_discord_id != loser_discord_id)
        )
    """)
    cur.execute("""CREATE INDEX idx_opponent_pending
                   ON match_confirmations(opponent_discord_id, status, expires_at)
                   WHERE status = 'pending'""")
    cur.execute("""CREATE INDEX idx_status_created
                   ON match_confirmations(status, created_at)""")
    cur.execute("""CREATE INDEX idx_submitter_recent
                   ON match_confirmations(submitter_discord_id, created_at DESC)""")

    # ── user_profiles ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE user_profiles (
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'discord',
            display_name TEXT NOT NULL,
            custom_display_name TEXT,
            avatar TEXT,
            email TEXT,
            email_verified INTEGER,
            first_login_at TEXT NOT NULL,
            last_login_at TEXT NOT NULL,
            discriminator TEXT,
            flags INTEGER,
            public_flags INTEGER,
            given_name TEXT,
            family_name TEXT,
            locale TEXT,
            raw_oauth_data TEXT,
            PRIMARY KEY (user_id, provider)
        )
    """)

    now = _now_iso()
    for uid, name in SAMPLE_PLAYERS:
        cur.execute(
            """INSERT INTO user_profiles
               (user_id, provider, display_name, avatar, first_login_at, last_login_at)
               VALUES (?,?,?,?,?,?)""",
            (uid, "discord", name, None, now, now),
        )

    # ── admin_audit_log ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            admin_id INTEGER NOT NULL,
            admin_name TEXT NOT NULL,
            action TEXT NOT NULL,
            target_id TEXT,
            target_name TEXT,
            previous_state TEXT,
            new_state TEXT,
            details TEXT
        )
    """)

    # ── seasons ──────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE seasons (
            season_id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id TEXT NOT NULL,
            creator_display_name TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            k_value INTEGER NOT NULL DEFAULT 32,
            base_elo INTEGER NOT NULL DEFAULT 1500,
            max_members INTEGER,
            region TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX idx_seasons_creator ON seasons(creator_id)")
    cur.execute("CREATE INDEX idx_seasons_status ON seasons(status)")

    cur.execute("""
        CREATE TABLE season_members (
            season_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            season_elo INTEGER NOT NULL DEFAULT 1500,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (season_id, user_id)
        )
    """)
    cur.execute("CREATE INDEX idx_season_members_user ON season_members(user_id)")

    cur.execute("""
        CREATE TABLE season_match_elo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            reporter_id TEXT,
            winner_id TEXT NOT NULL,
            loser_id TEXT NOT NULL,
            winner_display_name TEXT NOT NULL,
            loser_display_name TEXT NOT NULL,
            did_win INTEGER NOT NULL,
            winner_went_first TEXT,
            loser_went_first TEXT,
            match_time INTEGER,
            match_comment TEXT,
            curiosa_url_winner TEXT,
            curiosa_url_loser TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT,
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,
            timestamp TEXT NOT NULL
        )
    """)

    # Insert a sample season with members
    season_start = (datetime.now() - timedelta(days=10)).isoformat()
    season_end = (datetime.now() + timedelta(days=20)).isoformat()
    cur.execute(
        """INSERT INTO seasons
           (creator_id, creator_display_name, title, description, start_date, end_date, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (SAMPLE_PLAYERS[0][0], SAMPLE_PLAYERS[0][1],
         "Test Season", "A sample season for local development",
         season_start, season_end, _now_iso()),
    )
    for uid, name in SAMPLE_PLAYERS[:5]:
        cur.execute(
            "INSERT INTO season_members (season_id, user_id, display_name, joined_at) VALUES (?,?,?,?)",
            (1, uid, name, _now_iso()),
        )

    # ── limited tables ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE limited_arena_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_display_name TEXT NOT NULL,
            deck_url TEXT NOT NULL,
            json_deck_data TEXT,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            starting_elo INTEGER NOT NULL DEFAULT 1500,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    cur.execute("""CREATE INDEX idx_limited_runs_user_status
                   ON limited_arena_runs(user_id, status)""")

    cur.execute("""
        CREATE TABLE limited_match_records (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER,
            winner_id INTEGER,
            winner_display_name TEXT,
            loser_id INTEGER,
            loser_display_name TEXT,
            did_win BOOLEAN,
            timestamp TEXT,
            first_player TEXT,
            match_time INTEGER,
            curiosa_url_winner TEXT,
            curiosa_url_loser TEXT,
            match_comment TEXT,
            json_deck_data_winner TEXT,
            json_deck_data_loser TEXT,
            winner_elo_change INTEGER,
            loser_elo_change INTEGER,
            winner_went_first TEXT,
            loser_went_first TEXT,
            winner_run_id INTEGER,
            loser_run_id INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE limited_active_pairings (
            pairing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            player1_id INTEGER NOT NULL,
            player2_id INTEGER NOT NULL,
            player1_deck_url TEXT,
            player2_deck_url TEXT,
            player1_run_id INTEGER,
            player2_run_id INTEGER,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """)

    conn.commit()
    conn.close()
    print(f"          25 matches, 5 archived, 10 profiles, 1 season")


# ─── fart_scores.db ──────────────────────────────────────────────────────────

def create_fart_db():
    """Create fart_scores.db with sample scores."""

    if FART_DB.exists():
        print(f"  SKIP  {FART_DB} already exists")
        return

    print(f"  CREATE  {FART_DB}")
    conn = sqlite3.connect(str(FART_DB))
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE fart_scores (
            user_id TEXT PRIMARY KEY,
            user_display_name TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            date_last_updated TEXT
        )
    """)

    for uid, name in SAMPLE_PLAYERS[:7]:
        score = random.randint(1, 150)
        last = (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat()
        cur.execute(
            "INSERT INTO fart_scores (user_id, user_display_name, score, date_last_updated) VALUES (?,?,?,?)",
            (uid, name, score, last),
        )

    conn.commit()
    conn.close()
    print(f"          7 fart scores")


# ─── community.db ────────────────────────────────────────────────────────────

def create_community_db():
    """Create community.db with community links and curio tables."""

    if COMMUNITY_DB.exists():
        print(f"  SKIP  {COMMUNITY_DB} already exists")
        return

    print(f"  CREATE  {COMMUNITY_DB}")
    conn = sqlite3.connect(str(COMMUNITY_DB))
    cur = conn.cursor()

    # ── discord_servers ──────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE discord_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            invite_url TEXT,
            state TEXT
        )
    """)
    cur.execute(
        "INSERT INTO discord_servers (name, description, invite_url, state) VALUES (?,?,?,?)",
        ("Sorcerers Summit", "Main community server", "https://discord.gg/example", "active"),
    )
    cur.execute(
        "INSERT INTO discord_servers (name, description, invite_url, state) VALUES (?,?,?,?)",
        ("Sorcery Competitive", "Competitive play server", "https://discord.gg/example2", "active"),
    )

    # ── youtube_channels ─────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE youtube_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            channel_id TEXT,
            channel_url TEXT
        )
    """)
    cur.execute(
        "INSERT INTO youtube_channels (name, channel_id, channel_url) VALUES (?,?,?)",
        ("Summit TCG", "UCexample123", "https://youtube.com/@summittcg"),
    )

    # ── websites ─────────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE websites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            url TEXT
        )
    """)
    cur.execute(
        "INSERT INTO websites (name, description, url) VALUES (?,?,?)",
        ("Curiosa.io", "Deck building and card database", "https://curiosa.io"),
    )

    # ── curio_sets ───────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE curio_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    now = _now_iso()
    for set_name in ("Alpha", "Beta", "Arthurian Legends", "Gothic"):
        cur.execute(
            "INSERT INTO curio_sets (name, is_default, created_at) VALUES (?,1,?)",
            (set_name, now),
        )

    # ── curio_entries ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE curio_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            number_pulled INTEGER NOT NULL,
            description TEXT NOT NULL,
            set_id INTEGER NOT NULL,
            image_filename TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (set_id) REFERENCES curio_sets(id)
        )
    """)
    cur.execute("CREATE INDEX idx_curio_entries_set_id ON curio_entries(set_id)")
    cur.execute("CREATE INDEX idx_curio_entries_updated_at ON curio_entries(updated_at DESC)")

    conn.commit()
    conn.close()
    print(f"          2 servers, 1 channel, 1 website, 4 curio sets")


# ─── Verification ────────────────────────────────────────────────────────────

def verify():
    """Verify all databases are accessible and have expected tables."""
    print("\nVerifying...")
    errors = []

    checks = [
        (ELO_DB, "overall_standings", "SELECT COUNT(*) FROM overall_standings"),
        (ELO_DB, "events", "SELECT COUNT(*) FROM events"),
        (ELO_DB, "paper_standings", "SELECT COUNT(*) FROM paper_standings"),
        (ELO_DB, "limited_elo", "SELECT COUNT(*) FROM limited_elo"),
        (MATCH_RECORDS_DB, "match_records", "SELECT COUNT(*) FROM match_records"),
        (MATCH_RECORDS_DB, "match_records_archive", "SELECT COUNT(*) FROM match_records_archive"),
        (MATCH_RECORDS_DB, "match_reports_web", "SELECT COUNT(*) FROM match_reports_web"),
        (MATCH_RECORDS_DB, "match_confirmations", "SELECT COUNT(*) FROM match_confirmations"),
        (MATCH_RECORDS_DB, "user_profiles", "SELECT COUNT(*) FROM user_profiles"),
        (MATCH_RECORDS_DB, "seasons", "SELECT COUNT(*) FROM seasons"),
        (MATCH_RECORDS_DB, "admin_audit_log", "SELECT COUNT(*) FROM admin_audit_log"),
        (MATCH_RECORDS_DB, "limited_arena_runs", "SELECT COUNT(*) FROM limited_arena_runs"),
        (FART_DB, "fart_scores", "SELECT COUNT(*) FROM fart_scores"),
        (COMMUNITY_DB, "discord_servers", "SELECT COUNT(*) FROM discord_servers"),
        (COMMUNITY_DB, "curio_sets", "SELECT COUNT(*) FROM curio_sets"),
    ]

    for db_path, table, query in checks:
        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.cursor().execute(query).fetchone()[0]
            conn.close()
            status = f"{count} rows" if count else "empty"
            print(f"  OK  {db_path.name}/{table}: {status}")
        except Exception as e:
            errors.append(f"{db_path.name}/{table}: {e}")
            print(f"  FAIL  {db_path.name}/{table}: {e}")

    return len(errors) == 0


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Seed databases for local web app development")
    print(f"Target directory: {BOT_DIR}\n")

    # Ensure discord-bot directory exists
    BOT_DIR.mkdir(parents=True, exist_ok=True)

    create_elo_db()
    create_match_records_db()
    create_fart_db()
    create_community_db()

    ok = verify()

    if ok:
        print("\nAll databases ready! Run the web app:")
        print("  cd web-app")
        print("  python app.py")
    else:
        print("\nSome checks failed - see errors above.")
        sys.exit(1)
