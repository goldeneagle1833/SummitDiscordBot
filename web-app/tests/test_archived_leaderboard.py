"""Past event leaderboards read the online event ladder from the archive."""

import sqlite3

from repositories.elo import EloRepository


ONLINE_COLUMNS = (
    "final_paper_event_elo",
    "final_paper_rank",
    "final_online_event_elo",
    "final_online_rank",
)


def _add_online_columns(elo_db):
    conn = sqlite3.connect(str(elo_db))
    for col in ONLINE_COLUMNS:
        conn.execute(f"ALTER TABLE event_standings_archive ADD COLUMN {col} INTEGER")
    conn.commit()
    conn.close()


def _archive(elo_db, rows, event_id=7):
    """rows: (user_id, name, final_event_elo, final_rank, online_elo, online_rank)."""
    conn = sqlite3.connect(str(elo_db))
    conn.executemany(
        """INSERT INTO event_standings_archive
           (user_id, event_id, user_display_name, final_event_elo, final_rank,
            final_online_event_elo, final_online_rank)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(uid, event_id, name, elo, rank, oelo, orank) for uid, name, elo, rank, oelo, orank in rows],
    )
    conn.commit()
    conn.close()


# What the old archiver wrote: the legacy pair is max(paper, online) with paper
# stuck at 1500, ranked by whichever list was higher. The online pair is right.
SEASON_7 = [
    ("1", "duckworthy_", 1773, 2, 1773, 1),
    ("2", "Geoffrey", 1744, 3, 1744, 2),
    ("3", "Seamoose", 1500, 1, 1492, 4),
    ("4", "Hicham", 1719, 6, 1719, 3),
    ("5", "pkbyron", 1500, 5, 1430, 5),
]


class TestArchivedEventLeaderboard:
    def test_orders_by_online_event_elo(self, elo_db):
        _add_online_columns(elo_db)
        _archive(elo_db, SEASON_7)

        rows = EloRepository(db_path=elo_db).get_archived_event_leaderboard(7)

        assert [(r["rank"], r["display_name"], r["event_elo"]) for r in rows] == [
            (1, "duckworthy_", 1773),
            (2, "Geoffrey", 1744),
            (3, "Hicham", 1719),
            (4, "Seamoose", 1492),
            (5, "pkbyron", 1430),
        ]

    def test_only_the_requested_event(self, elo_db):
        _add_online_columns(elo_db)
        _archive(elo_db, SEASON_7)
        _archive(elo_db, [("9", "Old", 1900, 1, 1900, 1)], event_id=6)

        rows = EloRepository(db_path=elo_db).get_archived_event_leaderboard(7)

        assert "Old" not in {r["display_name"] for r in rows}

    def test_falls_back_to_legacy_columns(self, elo_db):
        # An archive from before dual ELO has only final_event_elo / final_rank
        conn = sqlite3.connect(str(elo_db))
        conn.executemany(
            """INSERT INTO event_standings_archive
               (user_id, event_id, user_display_name, final_event_elo, final_rank)
               VALUES (?, 3, ?, ?, ?)""",
            [("1", "A", 1550, 2), ("2", "B", 1600, 1)],
        )
        conn.commit()
        conn.close()

        rows = EloRepository(db_path=elo_db).get_archived_event_leaderboard(3)

        assert [(r["rank"], r["display_name"], r["event_elo"]) for r in rows] == [(1, "B", 1600), (2, "A", 1550)]

    def test_rows_with_null_online_columns_use_legacy_values(self, elo_db):
        _add_online_columns(elo_db)
        conn = sqlite3.connect(str(elo_db))
        conn.executemany(
            """INSERT INTO event_standings_archive
               (user_id, event_id, user_display_name, final_event_elo, final_rank)
               VALUES (?, 3, ?, ?, ?)""",
            [("1", "A", 1550, 2), ("2", "B", 1600, 1)],
        )
        conn.commit()
        conn.close()

        rows = EloRepository(db_path=elo_db).get_archived_event_leaderboard(3)

        assert [(r["display_name"], r["event_elo"]) for r in rows] == [("B", 1600), ("A", 1550)]

    def test_empty_without_archive_table(self, elo_db):
        conn = sqlite3.connect(str(elo_db))
        conn.execute("DROP TABLE event_standings_archive")
        conn.commit()
        conn.close()

        repo = EloRepository(db_path=elo_db)

        assert repo.get_archived_event_leaderboard(7) == []
        assert repo.get_player_event_elo("1", 7) is None

    def test_player_event_elo_matches_leaderboard_place(self, elo_db):
        _add_online_columns(elo_db)
        _archive(elo_db, SEASON_7)
        repo = EloRepository(db_path=elo_db)

        assert repo.get_player_event_elo("3", 7) == {"elo": 1492, "rank": 4, "display_name": "Seamoose"}
        assert repo.get_player_event_elo("1", 7)["rank"] == 1
        assert repo.get_player_event_elo("9", 7) is None


def _create_match_archive(match_db, with_source=True):
    conn = sqlite3.connect(str(match_db))
    source_col = ", source TEXT DEFAULT 'Discord'" if with_source else ""
    conn.execute(
        f"""CREATE TABLE match_records_archive (
                archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                winner_id TEXT,
                winner_display_name TEXT,
                losser_id TEXT,
                losser_display_name TEXT,
                timestamp TEXT
                {source_col}
            )"""
    )
    conn.commit()
    conn.close()


def _archive_match(match_db, event_id, winner, loser, source=None):
    conn = sqlite3.connect(str(match_db))
    if source is None:
        conn.execute(
            "INSERT INTO match_records_archive (event_id, winner_id, losser_id, timestamp) VALUES (?, ?, ?, '2026-09-01T12:00:00')",
            (event_id, winner, loser),
        )
    else:
        conn.execute(
            "INSERT INTO match_records_archive (event_id, winner_id, losser_id, timestamp, source) VALUES (?, ?, ?, '2026-09-01T12:00:00', ?)",
            (event_id, winner, loser, source),
        )
    conn.commit()
    conn.close()


def _add_event(elo_db, event_id, name):
    conn = sqlite3.connect(str(elo_db))
    conn.execute(
        "INSERT INTO events (event_id, event_name, start_date, end_date, is_active) VALUES (?, ?, '2026-08-30', '2026-09-28', 0)",
        (event_id, name),
    )
    conn.commit()
    conn.close()


class TestArchivedLeaderboardRoute:
    def test_carries_records_from_the_match_archive(self, client, elo_db, match_db):
        _add_online_columns(elo_db)
        _archive(elo_db, SEASON_7)
        _add_event(elo_db, 7, "Season 7")
        _create_match_archive(match_db)
        _archive_match(match_db, 7, "1", "3")
        _archive_match(match_db, 7, "1", "2")
        _archive_match(match_db, 7, "2", "3")
        _archive_match(match_db, 7, "1", "2", source="Bracket")  # postseason, not a season game
        _archive_match(match_db, 6, "3", "1")  # another event

        data = client.get("/api/leaderboard/archived/7").get_json()

        assert data["event_info"]["event_name"] == "Season 7"
        assert data["event_info"]["value_label"] == "Event ELO"
        assert data["total_matches"] == 3
        by_name = {r["display_name"]: r for r in data["leaderboard"]}
        assert [r["display_name"] for r in data["leaderboard"]][:3] == ["duckworthy_", "Geoffrey", "Hicham"]
        assert (by_name["duckworthy_"]["wins"], by_name["duckworthy_"]["losses"]) == (2, 0)
        assert (by_name["Geoffrey"]["wins"], by_name["Geoffrey"]["losses"]) == (1, 1)
        assert (by_name["Seamoose"]["wins"], by_name["Seamoose"]["losses"]) == (0, 2)
        assert "wins" not in by_name["pkbyron"]

    def test_archive_without_a_source_column(self, client, elo_db, match_db):
        _add_online_columns(elo_db)
        _archive(elo_db, SEASON_7)
        _create_match_archive(match_db, with_source=False)
        _archive_match(match_db, 7, "1", "3")

        data = client.get("/api/leaderboard/archived/7").get_json()

        assert data["total_matches"] == 1
        by_name = {r["display_name"]: r for r in data["leaderboard"]}
        assert by_name["duckworthy_"]["wins"] == 1

    def test_without_a_match_archive(self, client, elo_db, match_db):
        _add_online_columns(elo_db)
        _archive(elo_db, SEASON_7)

        resp = client.get("/api/leaderboard/archived/7")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["event_info"] is None
        assert data["total_matches"] == 0
        assert [r["display_name"] for r in data["leaderboard"]][:2] == ["duckworthy_", "Geoffrey"]
        assert "wins" not in data["leaderboard"][0]

    def test_season_filter_leaderboard_carries_records(self, client, match_db):
        conn = sqlite3.connect(str(match_db))
        conn.executemany(
            """INSERT INTO match_records
               (winner_id, winner_display_name, losser_id, losser_display_name, timestamp, source)
               VALUES (?, ?, ?, ?, ?, 'Discord')""",
            [
                ("1", "Ann", "2", "Ben", "2026-01-10T10:00:00"),
                ("1", "Ann", "3", "Cy", "2026-01-11T10:00:00"),
                ("2", "Ben", "3", "Cy", "2026-01-12T10:00:00"),
                ("3", "Cy", "1", "Ann", "2026-03-01T10:00:00"),  # after the season
            ],
        )
        conn.commit()
        conn.close()

        data = client.get("/api/leaderboard/archived/season/season_gothic_1").get_json()

        assert data["event_info"]["value_label"] == "Wins"
        assert data["total_matches"] == 3
        assert [(r["rank"], r["display_name"], r["event_elo"], r["wins"], r["losses"]) for r in data["leaderboard"]] == [
            (1, "Ann", 2, 2, 0),
            (2, "Ben", 1, 1, 1),
            (3, "Cy", 0, 0, 2),
        ]


class TestEventsSummaries:
    def test_ended_events_carry_players_champion_and_matches(self, client, elo_db, match_db):
        _add_online_columns(elo_db)
        _archive(elo_db, SEASON_7)
        _archive(elo_db, [("9", "Old", 1900, 1, 1900, 1), ("8", "Older", 1700, 2, 1700, 2)], event_id=6)
        _add_event(elo_db, 6, "Season 6")
        _add_event(elo_db, 7, "Season 7")
        conn = sqlite3.connect(str(elo_db))
        conn.execute("INSERT INTO events (event_id, event_name, start_date, is_active) VALUES (8, 'Season 8', '2026-09-29', 1)")
        conn.commit()
        conn.close()
        _create_match_archive(match_db)
        _archive_match(match_db, 7, "1", "3")
        _archive_match(match_db, 7, "2", "3")
        _archive_match(match_db, 7, "1", "2", source="Bracket")
        _archive_match(match_db, 6, "9", "8")

        data = client.get("/api/events").get_json()

        by_id = {e["event_id"]: e for e in data["events"]}
        assert (by_id[7]["players"], by_id[7]["champion"], by_id[7]["champion_id"], by_id[7]["matches"]) == (5, "duckworthy_", "1", 2)
        assert (by_id[6]["players"], by_id[6]["champion"], by_id[6]["matches"]) == (2, "Old", 1)
        assert (by_id[8]["players"], by_id[8]["champion"], by_id[8]["matches"]) == (None, None, None)
        # Season date-range filters have no archive
        assert by_id["season_gothic_1"]["is_active"] is False
        assert "players" not in by_id["season_gothic_1"]

    def test_events_without_any_archive(self, client, elo_db, match_db):
        _add_event(elo_db, 7, "Season 7")

        data = client.get("/api/events").get_json()

        season_7 = next(e for e in data["events"] if e["event_id"] == 7)
        assert (season_7["players"], season_7["champion"], season_7["matches"]) == (None, None, None)
