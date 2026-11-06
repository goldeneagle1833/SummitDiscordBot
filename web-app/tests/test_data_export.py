"""Tests for the owner-only "Export my data" download."""

import io
import json
import sqlite3
import zipfile

URL = "/api/player/{}/data-export"

# match_records exactly as the bot builds it in production
# (discord-bot/repositories/elo_repo.py create_db + its ALTER TABLE migrations).
PROD_MATCH_RECORDS = """
    CREATE TABLE match_records (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER, winner_id INTEGER, winner_display_name TEXT,
        losser_id INTEGER, losser_display_name TEXT, did_win BOOLEAN,
        timestamp TEXT, first_player TEXT, match_time INTEGER, curiosa_url TEXT,
        match_comment TEXT, json_deck_data TEXT,
        winner_elo_change INTEGER, loser_elo_change INTEGER,
        winner_lifetime_elo_change INTEGER, loser_lifetime_elo_change INTEGER,
        curiosa_url_winner TEXT, curiosa_url_loser TEXT,
        json_deck_data_winner TEXT, json_deck_data_loser TEXT,
        winner_went_first TEXT, loser_went_first TEXT,
        source TEXT DEFAULT 'Discord', match_type TEXT DEFAULT 'ranked',
        voice INTEGER NOT NULL DEFAULT 0, pairing_id INTEGER, replay_url TEXT,
        winner_lifetime_elo_after INTEGER, loser_lifetime_elo_after INTEGER,
        winner_avatar TEXT, loser_avatar TEXT,
        winner_avatar_elo_change INTEGER, loser_avatar_elo_change INTEGER,
        winner_avatar_elo_after INTEGER, loser_avatar_elo_after INTEGER,
        event_k INTEGER
    )
"""

ME = "111111111111111111"
OPP = "222222222222222222"


def _seed(match_db, elo_db):
    conn = sqlite3.connect(str(match_db))
    conn.execute("DROP TABLE IF EXISTS match_records")
    conn.execute(PROD_MATCH_RECORDS)
    conn.execute("CREATE TABLE IF NOT EXISTS match_records_archive AS SELECT * FROM match_records WHERE 0")
    rows = [
        # I won, I reported (legacy deck column is mine)
        (ME, ME, "Me", OPP, "Opp", "2026-11-01T10:00:00", 12, -12,
         "https://curiosa.io/decks/MINE", "https://curiosa.io/decks/THEIRS",
         '{"avatar": "Sparkmage"}', '{"avatar": "SECRET_OPP_DECK"}',
         "legacy-mine", "gg", "Sparkmage", "Seer"),
        # I lost, opponent reported (their legacy deck + comment stay out)
        (OPP, OPP, "Opp", ME, "Me", "2026-11-02T10:00:00", 10, -10,
         "https://curiosa.io/decks/THEIRS2", "https://curiosa.io/decks/MINE2",
         '{"avatar": "SECRET_OPP_DECK2"}', '{"avatar": "Sparkmage"}',
         "legacy-theirs", "opp private comment", "Seer", "Sparkmage"),
        # Someone else's match
        (OPP, OPP, "Opp", "333", "Other", "2026-11-03T10:00:00", 8, -8,
         None, None, None, None, None, None, None, None),
    ]
    for r in rows:
        conn.execute(
            """INSERT INTO match_records (reporter_id, winner_id, winner_display_name,
                losser_id, losser_display_name, timestamp, winner_elo_change, loser_elo_change,
                curiosa_url_winner, curiosa_url_loser, json_deck_data_winner, json_deck_data_loser,
                json_deck_data, match_comment, winner_avatar, loser_avatar)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            r,
        )
    # A future season table with its own name, same winner/loser columns
    conn.execute(
        "CREATE TABLE glicko_s9_matches (id INTEGER PRIMARY KEY, winner_id TEXT, loser_id TEXT, "
        "winner_display_name TEXT, loser_display_name TEXT, winner_rating_after REAL, "
        "loser_rating_after REAL, loser_deck_url TEXT, timestamp TEXT)"
    )
    conn.execute(
        "INSERT INTO glicko_s9_matches VALUES (1, ?, ?, 'Opp', 'Me', 1600, 1480, 'MY_S9_DECK', '2026-11-20T10:00:00')",
        (OPP, ME),
    )
    conn.execute(
        "INSERT INTO user_profiles (user_id, provider, display_name, email, first_login_at, last_login_at, raw_oauth_data) "
        "VALUES (?, 'discord', 'Me', 'me@example.com', '2026-01-01', '2026-11-01', '{\"token\": \"x\"}')",
        (ME,),
    )
    conn.commit()
    conn.close()

    from repositories.blocked_users_repo import BlockedUsersRepository
    from repositories.player_kudos_repo import PlayerKudosRepository
    BlockedUsersRepository()  # creates the table
    PlayerKudosRepository(match_db)
    conn = sqlite3.connect(str(match_db))
    conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id, reason) VALUES (?, ?, 'mine')", (ME, OPP))
    conn.execute("INSERT INTO blocked_users (user_id, blocked_user_id, reason) VALUES (?, ?, 'theirs')", (OPP, ME))
    conn.execute(
        "INSERT INTO player_kudos (giver_id, giver_name, receiver_id, receiver_name, match_id, reasons, anonymous) "
        "VALUES (?, 'Opp', ?, 'Me', 1, '[\"good_sport\"]', 1)", (OPP, ME))
    conn.execute(
        "INSERT INTO player_kudos (giver_id, giver_name, receiver_id, receiver_name, match_id, reasons, anonymous) "
        "VALUES (?, 'Me', ?, 'Opp', 2, '[\"fun\"]', 0)", (ME, OPP))
    conn.commit()
    conn.close()

    conn = sqlite3.connect(str(elo_db))
    conn.execute("INSERT INTO overall_standings (user_id, user_display_name, online_elo) VALUES (?, 'Me', 1612)", (ME,))
    conn.execute("INSERT INTO overall_standings (user_id, user_display_name, online_elo) VALUES (?, 'Opp', 1700)", (OPP,))
    conn.commit()
    conn.close()


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "Me"


def _download(client, player_id=ME):
    resp = client.get(URL.format(player_id))
    assert resp.status_code == 200, resp.get_json()
    assert resp.mimetype == "application/zip"
    assert "attachment" in resp.headers["Content-Disposition"]
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert set(zf.namelist()) == {"summit-data.json", "matches.csv", "README.txt"}
    return json.loads(zf.read("summit-data.json")), zf.read("matches.csv").decode()


def test_needs_login(client):
    assert client.get(URL.format(ME)).status_code == 401


def test_only_your_own_data(client, match_db, elo_db):
    _seed(match_db, elo_db)
    _login(client, OPP)
    assert client.get(URL.format(ME)).status_code == 403


def test_admin_cannot_export_someone_else(admin_session, match_db, elo_db):
    _seed(match_db, elo_db)
    assert admin_session.get(URL.format(ME)).status_code == 403


def test_api_key_alone_is_not_enough(client):
    assert client.get(URL.format(ME), headers={"X-API-Key": "test-api-key-123"}).status_code == 401


def test_export_contents(client, match_db, elo_db):
    _seed(match_db, elo_db)
    _login(client, ME)
    data, matches_csv = _download(client)
    raw = json.dumps(data)

    assert data["player_id"] == ME
    assert data["summary"] == {"matches": 3, "wins": 1, "losses": 2}
    assert [m["table"] for m in data["matches"]][0] == "glicko_s9_matches"

    by_ts = {m["timestamp"]: m for m in data["matches"]}
    won = by_ts["2026-11-01T10:00:00"]
    assert won["result"] == "win"
    assert won["match_id"] == 1
    assert won["my_elo_change"] == 12
    assert won["my_curiosa_url"] == "https://curiosa.io/decks/MINE"
    assert won["my_json_deck_data"] == {"avatar": "Sparkmage"}
    assert won["my_avatar"] == "Sparkmage" and won["opponent_avatar"] == "Seer"
    assert won["opponent_display_name"] == "Opp"
    assert won["json_deck_data"] == "legacy-mine"  # I reported it
    assert "opponent_curiosa_url" not in won and "opponent_elo_change" not in won

    lost = by_ts["2026-11-02T10:00:00"]
    assert lost["result"] == "loss"
    assert lost["my_curiosa_url"] == "https://curiosa.io/decks/MINE2"
    assert "json_deck_data" not in lost and "match_comment" not in lost

    s9 = by_ts["2026-11-20T10:00:00"]
    assert s9["my_rating_after"] == 1480 and s9["my_deck_url"] == "MY_S9_DECK"
    assert "opponent_rating_after" not in s9

    # Other players' private data never appears
    for secret in ("THEIRS", "SECRET_OPP_DECK", "legacy-theirs", "opp private comment", "Other", "1700"):
        assert secret not in raw, secret

    assert data["profile"]["user_profiles"][0]["email"] == "me@example.com"
    assert "raw_oauth_data" not in data["profile"]["user_profiles"][0]
    assert data["ratings"]["overall_standings"] == [
        {"user_id": ME, "user_display_name": "Me", "online_elo": 1612, "online_event_elo": 1500,
         "paper_elo": 1500, "paper_event_elo": 1500}
    ]
    assert [b["blocked_user_id"] for b in data["settings"]["blocked_users"]] == [OPP]
    assert data["kudos"]["received"][0]["giver_name"] == "Anonymous"
    assert "giver_id" not in data["kudos"]["received"][0]
    assert data["kudos"]["given"][0]["receiver_id"] == OPP

    header = matches_csv.splitlines()[0]
    assert header.startswith("timestamp,table,match_id,result")
    assert len(matches_csv.strip().splitlines()) == 4


def test_google_prefix(client, match_db, elo_db):
    _seed(match_db, elo_db)
    _login(client, f"google_{ME}")
    data, _ = _download(client, ME)
    assert data["summary"]["matches"] == 3


def test_export_is_audit_logged(client, match_db, elo_db):
    _seed(match_db, elo_db)
    _login(client, ME)
    _download(client)
    conn = sqlite3.connect(str(match_db))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    table = "admin_audit_log" if "admin_audit_log" in tables else "audit_log"
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    action_col = "action_type" if "action_type" in cols else "action"
    n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {action_col} = 'self_data_export'").fetchone()[0]
    conn.close()
    assert n == 1
