"""Season 8 PSO game lookup backfill: stored answers, play/draw fill, own-replay-only links."""

import importlib.util
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

from repositories.pso_game_lookups import PsoGameLookupRepository
from tests.conftest import seed_elo_data, seed_matches

ALICE, BOB, CAROL = "111111111111111111", "222222222222222222", "333333333333333333"
ALICE_VIEW = "https://playsorceryonline.com/replays/replay_alice"
BOB_VIEW = "https://playsorceryonline.com/replays/replay_bob"

_spec = importlib.util.spec_from_file_location(
    "pso_season8_backfill", Path(__file__).resolve().parent.parent / "scripts" / "pso_season8_backfill.py"
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def _found(winner=ALICE, winner_first=True, matched_by="both_players", pso_winner=ALICE):
    return {
        "status": "found",
        "game": {
            "id": "seg_1", "matchedBy": matched_by,
            "startedAt": "2026-10-05T19:00:00.000Z", "finishedAt": "2026-10-05T19:25:00.000Z",
            "durationSeconds": 1500, "minutesFromPlayedAt": 7, "source": "pso", "queueType": "ranked",
            "winnerDiscordId": pso_winner,
            "players": [
                {"discordId": ALICE, "result": "win", "wentFirst": winner_first,
                 "avatar": "Sparkmage", "replayUrl": ALICE_VIEW},
                {"discordId": BOB, "result": "loss", "wentFirst": not winner_first,
                 "avatar": "Geomancer", "replayUrl": BOB_VIEW},
            ],
            "replayUrl": ALICE_VIEW,
        },
    }


def _season(match_db, elo_db, n=1):
    seed_elo_data(elo_db, [{"user_id": ALICE, "name": "Alice"}, {"user_id": BOB, "name": "Bob"}])
    conn = sqlite3.connect(str(elo_db))
    conn.execute("INSERT INTO events (event_id, event_name, start_date, is_active)"
                 " VALUES (8, 'Gothic Season 8', '2026-10-02T12:05:29', 1)")
    conn.commit()
    conn.close()
    seed_matches(match_db, [{"winner_id": ALICE, "loser_id": BOB, "timestamp": "2026-10-05T19:32:00"}] * n)
    conn = sqlite3.connect(str(match_db))
    for col in ("replay_url", "winner_went_first", "loser_went_first"):
        try:
            conn.execute(f"ALTER TABLE match_records ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def _store(match_db, body, match_id=1):
    repo = PsoGameLookupRepository(match_db)
    repo.ensure_table()
    m = {"match_id": match_id, "winner_id": ALICE, "loser_id": BOB}
    repo.save(backfill.row_from_answer(m, "2026-10-05T19:32:00Z", body))
    return repo


def test_played_at_sends_utc_with_zone():
    assert backfill.played_at("2026-10-05T19:32:00.123456", ZoneInfo("UTC")) == "2026-10-05T19:32:00Z"
    assert backfill.played_at("2026-10-05 15:32:00", ZoneInfo("America/New_York")) == "2026-10-05T19:32:00Z"


def test_every_answer_is_stored_and_not_asked_again(match_db, elo_db, app):
    _season(match_db, elo_db, n=3)
    repo = _store(match_db, _found(), 1)
    _store(match_db, {"status": "not_found"}, 2)
    _store(match_db, {"status": "ambiguous", "candidates": 2}, 3)
    rows = {r["match_id"]: r for r in repo.all()}
    assert rows[1]["winner_replay_url"] == ALICE_VIEW and rows[1]["loser_replay_url"] == BOB_VIEW
    assert rows[1]["winner_went_first"] == 1 and rows[1]["winner_avatar"] == "Sparkmage"
    assert rows[3]["candidates"] == 2
    matches = backfill.season_matches(str(match_db), "2026-10-02T12:05:29", None)
    todo, _ = backfill.to_be_looked_up(matches, repo, retry_unanswered=False)
    assert todo == []
    todo, _ = backfill.to_be_looked_up(matches, repo, retry_unanswered=True)
    assert [m["match_id"] for m in todo] == [2, 3]


def test_apply_fills_play_draw_only_when_safe(match_db, elo_db, app):
    _season(match_db, elo_db, n=4)
    _store(match_db, _found(winner_first=False), 1)
    _store(match_db, _found(pso_winner=BOB), 2)                  # PSO disagrees on winner
    _store(match_db, _found(matched_by="one_player"), 3)         # opponent was a guest
    repo = _store(match_db, _found(), 4)
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE match_records SET winner_went_first = 'n', loser_went_first = 'y' WHERE rowid = 4")
    conn.commit()
    conn.close()
    matches = backfill.season_matches(str(match_db), "2026-10-02T12:05:29", None)
    updates, counts = backfill.apply_plan(repo, matches, include_one_player=False)
    assert updates == [("n", "y", 1)]
    assert counts["skipped: PSO winner disagrees"] == 1
    assert counts["skipped: one player was a guest"] == 1
    assert counts["Summit already has play/draw"] == 1


def _profile_replays(client, player_id=ALICE):
    resp = client.get(f"/api/player/{player_id}")
    assert resp.status_code == 200
    return [m["replay_url"] for m in resp.get_json()["matches"]]


def _as(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_backfilled_replay_shown_to_each_player_as_their_own_view(client, match_db, elo_db):
    _season(match_db, elo_db)
    _store(match_db, _found())
    assert _profile_replays(client) == [None]       # logged out
    _as(client, ALICE)
    assert _profile_replays(client) == [ALICE_VIEW]
    _as(client, BOB)                                # opponent sees their own view
    assert _profile_replays(client) == [BOB_VIEW]
    _as(client, CAROL)
    assert _profile_replays(client) == [None]
    _as(client, "admin_user_1")                     # not even admins
    assert _profile_replays(client) == [None]


def test_existing_summit_replay_still_wins(client, match_db, elo_db):
    _season(match_db, elo_db)
    _store(match_db, _found())
    conn = sqlite3.connect(str(match_db))
    conn.execute("UPDATE match_records SET replay_url = 'https://playsorceryonline.com/replay/table'")
    conn.commit()
    conn.close()
    _as(client, BOB)
    assert _profile_replays(client) == ["https://playsorceryonline.com/replay/table"]


def test_match_history_page_shows_only_own_view(client, match_db, elo_db):
    _season(match_db, elo_db)
    _store(match_db, _found())
    _as(client, BOB)
    rows = client.get("/api/match-history?date=2026-10-05").get_json()
    assert [m["replay_url"] for m in rows] == [BOB_VIEW]
    _as(client, CAROL)
    rows = client.get("/api/match-history?date=2026-10-05").get_json()
    assert [m["replay_url"] for m in rows] == [None]
