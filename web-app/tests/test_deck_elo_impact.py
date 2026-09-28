"""Per-deck ELO impact on the profile's Recent Decks section.

Both figures sum the per-match *lifetime* ELO deltas: "season" over the
active event's window, "lifetime" over every match in scope.
"""
import json
import sqlite3

DECK = "https://playsorceryonline.com/?deck=pD-1gXa3cg8c"
DECK_JSON = json.dumps({
    "name": "Earth/Fire",
    "avatar": [{"name": "Sorcerer", "type": "Avatar"}],
    "spellbook": [], "atlas": [], "sideboard": [],
})


def _record(conn, match_id, winner, loser, winner_url, loser_url, ts,
            winner_change=10, loser_change=-10, lifetime=None):
    cols = ("match_id, winner_id, winner_display_name, losser_id, losser_display_name, "
            "timestamp, winner_elo_change, loser_elo_change, curiosa_url, "
            "curiosa_url_winner, curiosa_url_loser, json_deck_data_winner, json_deck_data_loser")
    values = [match_id, winner, f"P{winner}", loser, f"P{loser}", ts, winner_change, loser_change,
              winner_url or loser_url, winner_url, loser_url,
              DECK_JSON if winner_url else "{}", DECK_JSON if loser_url else "{}"]
    if lifetime is not None:
        cols += ", winner_lifetime_elo_change, loser_lifetime_elo_change"
        values += list(lifetime)
    conn.execute(f"INSERT INTO match_records ({cols}) VALUES ({', '.join('?' * len(values))})", values)


def _active_event(elo_db, start, end=None):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_name, start_date, end_date, is_active) VALUES (?, ?, ?, 1)",
        ("Season 7", start, end),
    )
    conn.commit()
    conn.close()


def _profile_decks(client, player_id="111", **params):
    with client.session_transaction() as sess:
        sess["user_id"] = player_id
        sess["username"] = f"P{player_id}"
    resp = client.get(f"/api/player/{player_id}", query_string=params)
    assert resp.status_code == 200, resp.get_json()
    return {d["url"]: d for d in resp.get_json()["recent_decks"]}


class TestDeckEloImpact:
    def test_season_sums_only_matches_inside_the_active_event(self, client, match_db, elo_db):
        _active_event(elo_db, "2026-08-01")
        conn = sqlite3.connect(str(match_db))
        # Pre-season win: lifetime only
        _record(conn, "m0", "111", "222", DECK, None, "2026-07-01 10:00:00", winner_change=15)
        # In-season: a win and a loss
        _record(conn, "m1", "111", "333", DECK, None, "2026-09-01 10:00:00", winner_change=10)
        _record(conn, "m2", "444", "111", None, DECK, "2026-09-02 10:00:00", loser_change=-12)
        conn.commit()
        conn.close()

        deck = _profile_decks(client)[DECK]
        assert (deck["wins"], deck["losses"]) == (2, 1)
        assert deck["elo_lifetime"] == 13
        assert deck["elo_season"] == -2
        assert (deck["season_wins"], deck["season_losses"]) == (1, 1)

    def test_uses_stored_lifetime_delta_over_event_delta(self, client, match_db, elo_db):
        _active_event(elo_db, "2026-08-01")
        conn = sqlite3.connect(str(match_db))
        conn.execute("ALTER TABLE match_records ADD COLUMN winner_lifetime_elo_change INTEGER")
        conn.execute("ALTER TABLE match_records ADD COLUMN loser_lifetime_elo_change INTEGER")
        # Event delta says +10, lifetime delta says +7: the deck figure uses lifetime
        _record(conn, "m1", "111", "222", DECK, None, "2026-09-01 10:00:00",
                winner_change=10, loser_change=-10, lifetime=(7, -7))
        # Older row without a stored lifetime delta falls back to the event delta
        _record(conn, "m2", "333", "111", None, DECK, "2026-09-02 10:00:00", loser_change=-4)
        conn.commit()
        conn.close()

        deck = _profile_decks(client)[DECK]
        assert deck["elo_lifetime"] == 3
        assert deck["elo_season"] == 3

    def test_no_active_event_means_no_season_figure(self, client, match_db, elo_db):
        conn = sqlite3.connect(str(match_db))
        _record(conn, "m1", "111", "222", DECK, None, "2026-09-01 10:00:00", winner_change=10)
        conn.commit()
        conn.close()

        deck = _profile_decks(client)[DECK]
        assert deck["elo_season"] is None
        assert deck["elo_lifetime"] == 10
        assert deck["season_wins"] == 0
