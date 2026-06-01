"""Service for admin operations on players and matches."""

import logging
import sqlite3

from repositories.elo import EloRepository
from repositories.matches import MatchRepository
from webapp_config import ELO_DB_PATH, MATCH_RECORDS_DB_PATH

logger = logging.getLogger(__name__)


class AdminService:
    """Business logic for admin operations."""

    def __init__(
        self,
        elo_repo: EloRepository | None = None,
        match_repo: MatchRepository | None = None,
    ):
        self._elo_repo = elo_repo or EloRepository()
        self._match_repo = match_repo or MatchRepository()

    def remove_player(self, user_id: str) -> dict:
        """Remove a player from both overall_standings and paper_standings.

        Match records are preserved for historical accuracy.
        """
        # Try bot standings first
        bot_elo = self._elo_repo.get_user_elo(user_id)
        paper_elo = self._elo_repo.get_user_paper_elo(str(user_id))

        if bot_elo is None and paper_elo is None:
            return {"success": False, "error": "Player not found in any standings"}

        removed_from = []
        if bot_elo is not None:
            if self._elo_repo.delete_player(user_id):
                removed_from.append(f"online (ELO {bot_elo})")
        if paper_elo is not None:
            if self._elo_repo.delete_paper_player(str(user_id)):
                removed_from.append(f"paper (ELO {paper_elo})")

        if removed_from:
            logger.info(f"Admin removed player {user_id} from: {', '.join(removed_from)}")
            return {"success": True, "message": f"Player removed from {', '.join(removed_from)}"}
        return {"success": False, "error": "Failed to remove player"}

    def remove_match(self, match_id: str) -> dict:
        """Delete a match and reverse ELO changes. Handles both bot and web matches."""
        is_web = str(match_id).startswith("web_")

        if is_web:
            return self._remove_web_match(match_id)
        else:
            return self._remove_bot_match(match_id)

    def _remove_bot_match(self, match_id: str) -> dict:
        """Remove a bot match (from match_records) and reverse ELO in overall_standings."""
        try:
            numeric_id = int(match_id)
        except (ValueError, TypeError):
            return {"success": False, "error": f"Invalid bot match ID: {match_id}"}

        match = self._match_repo.get_match_full_details(numeric_id)
        if not match:
            return {"success": False, "error": f"Match #{match_id} not found in bot records"}

        winner_id = match["winner_id"]
        loser_id = match["loser_id"]
        winner_elo_change = match["winner_elo_change"]
        loser_elo_change = match["loser_elo_change"]

        # Reverse ELO for winner
        try:
            winner_current = self._elo_repo.get_user_elo(winner_id)
            if winner_current is not None:
                new_winner_elo = winner_current - winner_elo_change
                self._elo_repo.upsert_user_elo(
                    winner_id, match["winner_name"] or f"User#{winner_id}", new_winner_elo
                )
        except Exception as e:
            logger.warning(f"Could not reverse winner ELO: {e}")

        # Reverse ELO for loser
        try:
            loser_current = self._elo_repo.get_user_elo(loser_id)
            if loser_current is not None:
                new_loser_elo = loser_current - loser_elo_change
                self._elo_repo.upsert_user_elo(
                    loser_id, match["loser_name"] or f"User#{loser_id}", new_loser_elo
                )
        except Exception as e:
            logger.warning(f"Could not reverse loser ELO: {e}")

        deleted = self._match_repo.delete_match(numeric_id)
        if deleted:
            logger.info(
                f"Admin removed bot match #{match_id}: "
                f"winner={winner_id} (ELO {winner_elo_change:+d} reversed), "
                f"loser={loser_id} (ELO {loser_elo_change:+d} reversed)"
            )
            return {
                "success": True,
                "message": f"Bot match #{match_id} deleted and ELO reversed",
                "winner_id": str(winner_id),
                "loser_id": str(loser_id),
                "winner_elo_reversed": winner_elo_change,
                "loser_elo_reversed": loser_elo_change,
            }
        return {"success": False, "error": "Failed to delete match record"}

    def _remove_web_match(self, match_id: str) -> dict:
        """Remove a web match (from match_reports_web) and reverse paper ELO."""
        match = self._match_repo.get_web_match_full_details(match_id)
        if not match:
            return {"success": False, "error": f"Match {match_id} not found in web records"}

        winner_id = str(match["winner_id"])
        loser_id = str(match["loser_id"])
        winner_elo_change = match["winner_elo_change"]
        loser_elo_change = match["loser_elo_change"]

        # Reverse paper ELO for winner
        winner_current = self._elo_repo.get_user_paper_elo(winner_id)
        if winner_current is not None:
            new_winner_elo = winner_current - winner_elo_change
            self._elo_repo.upsert_paper_elo(
                winner_id, match["winner_name"] or f"User#{winner_id}", new_winner_elo
            )

        # Reverse paper ELO for loser
        loser_current = self._elo_repo.get_user_paper_elo(loser_id)
        if loser_current is not None:
            new_loser_elo = loser_current - loser_elo_change
            self._elo_repo.upsert_paper_elo(
                loser_id, match["loser_name"] or f"User#{loser_id}", new_loser_elo
            )

        deleted = self._match_repo.delete_web_match(match_id)
        if deleted:
            logger.info(
                f"Admin removed web match {match_id}: "
                f"winner={winner_id} (paper ELO {winner_elo_change:+d} reversed), "
                f"loser={loser_id} (paper ELO {loser_elo_change:+d} reversed)"
            )
            return {
                "success": True,
                "message": f"Web match {match_id} deleted and paper ELO reversed",
                "winner_id": winner_id,
                "loser_id": loser_id,
                "winner_elo_reversed": winner_elo_change,
                "loser_elo_reversed": loser_elo_change,
            }
        return {"success": False, "error": "Failed to delete web match record"}

    def reset_player_elo(self, user_id: str, new_elo: int = 1500, source: str = "both") -> dict:
        """Set a player's ELO to a specified value.

        Args:
            user_id: Player ID (str to support google_ prefix)
            new_elo: New ELO value
            source: Which standings to reset - 'bot', 'paper', or 'both'
        """
        results = []

        if source in ("bot", "both"):
            current_bot = self._elo_repo.get_user_elo(user_id)
            if current_bot is not None:
                if self._elo_repo.reset_player_elo(user_id, new_elo):
                    results.append(f"online: {current_bot} -> {new_elo}")

        if source in ("paper", "both"):
            current_paper = self._elo_repo.get_user_paper_elo(str(user_id))
            if current_paper is not None:
                if self._elo_repo.reset_paper_elo(str(user_id), new_elo):
                    results.append(f"paper: {current_paper} -> {new_elo}")

        if not results:
            return {"success": False, "error": "Player not found in standings"}

        msg = "ELO updated - " + ", ".join(results)
        logger.info(f"Admin set ELO for {user_id}: {msg}")
        return {"success": True, "message": msg}

    def transfer_history(self, old_user_id: str, new_user_id: str) -> dict:
        """Transfer all history from old_user_id to new_user_id across all tables.

        Updates every table that references a player ID so the new account
        inherits the old account's full history.
        """
        if old_user_id == new_user_id:
            return {"success": False, "error": "Source and destination accounts are the same"}

        updates = {}

        def _update_cols(cur, table, columns, new_id, old_id):
            """Update columns in a table, skipping columns that don't exist."""
            count = 0
            for col in columns:
                try:
                    cur.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new_id, old_id))
                    count += cur.rowcount
                except sqlite3.OperationalError:
                    pass  # Column doesn't exist in this schema version
            return count

        # ── match_records.db tables ──
        try:
            conn = sqlite3.connect(str(MATCH_RECORDS_DB_PATH))
            cur = conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}

            # match_records + archive: winner_id, losser_id, reporter_id
            for table in ("match_records", "match_records_archive"):
                if table not in tables:
                    continue
                count = _update_cols(cur, table, ("winner_id", "losser_id", "reporter_id"), new_user_id, old_user_id)
                updates[table] = count

            # match_reports_web: winner_id, losser_id, reporter_id
            if "match_reports_web" in tables:
                count = _update_cols(cur, "match_reports_web", ("winner_id", "losser_id", "reporter_id"), new_user_id, old_user_id)
                updates["match_reports_web"] = count

            # rumble_match_records: winner_id, losser_id, reporter_id
            if "rumble_match_records" in tables:
                count = _update_cols(cur, "rumble_match_records", ("winner_id", "losser_id", "reporter_id"), new_user_id, old_user_id)
                updates["rumble_match_records"] = count

            # match_confirmations: reporter_id, winner_id, loser_id
            if "match_confirmations" in tables:
                count = _update_cols(cur, "match_confirmations", ("reporter_id", "winner_id", "loser_id"), new_user_id, old_user_id)
                updates["match_confirmations"] = count

            # pairings: player_1_id, player_2_id
            if "pairings" in tables:
                count = _update_cols(cur, "pairings", ("player_1_id", "player_2_id"), new_user_id, old_user_id)
                updates["pairings"] = count

            # season_members: user_id (UNIQUE on user_id+season_id)
            if "season_members" in tables:
                try:
                    cur.execute("UPDATE season_members SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["season_members"] = cur.rowcount
                except sqlite3.IntegrityError:
                    updates["season_members"] = "skipped (new user already in season)"

            # season_match_elo: reporter_id, winner_id, loser_id
            if "season_match_elo" in tables:
                count = _update_cols(cur, "season_match_elo", ("reporter_id", "winner_id", "loser_id"), new_user_id, old_user_id)
                updates["season_match_elo"] = count

            # creator_access: user_id
            if "creator_access" in tables:
                try:
                    cur.execute("UPDATE creator_access SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["creator_access"] = cur.rowcount
                except sqlite3.IntegrityError:
                    cur.execute("DELETE FROM creator_access WHERE user_id = ?", (old_user_id,))
                    updates["creator_access"] = "merged (new user already had access)"

            # curio_entries: user_id
            if "curio_entries" in tables:
                try:
                    cur.execute("UPDATE curio_entries SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["curio_entries"] = cur.rowcount
                except sqlite3.OperationalError:
                    pass

            # user_profiles: user_id (PRIMARY KEY)
            if "user_profiles" in tables:
                cur.execute("SELECT 1 FROM user_profiles WHERE user_id = ?", (new_user_id,))
                new_exists = cur.fetchone() is not None
                if new_exists:
                    cur.execute("DELETE FROM user_profiles WHERE user_id = ?", (old_user_id,))
                    updates["user_profiles"] = "old profile removed (new profile kept)"
                else:
                    cur.execute("UPDATE user_profiles SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["user_profiles"] = cur.rowcount

            # limited tables in match_records.db
            if "limited_match_records" in tables:
                count = _update_cols(cur, "limited_match_records", ("winner_id", "loser_id", "reporter_id"), new_user_id, old_user_id)
                updates["limited_match_records"] = count

            if "limited_arena_runs" in tables:
                try:
                    cur.execute("UPDATE limited_arena_runs SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["limited_arena_runs"] = cur.rowcount
                except sqlite3.OperationalError:
                    pass

            if "limited_active_pairings" in tables:
                count = _update_cols(cur, "limited_active_pairings", ("player_1_id", "player_2_id"), new_user_id, old_user_id)
                updates["limited_active_pairings"] = count

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to transfer match_records.db: {e}")
            return {"success": False, "error": f"Failed during match records transfer: {e}"}

        # ── elo.db tables ──
        try:
            conn = sqlite3.connect(str(ELO_DB_PATH))
            cur = conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}

            # overall_standings: user_id (PRIMARY KEY)
            if "overall_standings" in tables:
                cur.execute("SELECT 1 FROM overall_standings WHERE user_id = ?", (new_user_id,))
                if cur.fetchone():
                    cur.execute("DELETE FROM overall_standings WHERE user_id = ?", (old_user_id,))
                    updates["overall_standings"] = "old removed (new user already has standings)"
                else:
                    cur.execute("UPDATE overall_standings SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["overall_standings"] = cur.rowcount

            # paper_standings: user_id (PRIMARY KEY)
            if "paper_standings" in tables:
                cur.execute("SELECT 1 FROM paper_standings WHERE user_id = ?", (new_user_id,))
                if cur.fetchone():
                    cur.execute("DELETE FROM paper_standings WHERE user_id = ?", (old_user_id,))
                    updates["paper_standings"] = "old removed (new user already has standings)"
                else:
                    cur.execute("UPDATE paper_standings SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["paper_standings"] = cur.rowcount

            # limited_elo: user_id
            if "limited_elo" in tables:
                cur.execute("SELECT 1 FROM limited_elo WHERE user_id = ?", (new_user_id,))
                if cur.fetchone():
                    cur.execute("DELETE FROM limited_elo WHERE user_id = ?", (old_user_id,))
                    updates["limited_elo"] = "old removed (new user already has limited elo)"
                else:
                    cur.execute("UPDATE limited_elo SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                    updates["limited_elo"] = cur.rowcount

            # event_standings_archive: user_id
            if "event_standings_archive" in tables:
                cur.execute("UPDATE event_standings_archive SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                updates["event_standings_archive"] = cur.rowcount

            # limited_event_standings_archive
            if "limited_event_standings_archive" in tables:
                cur.execute("UPDATE limited_event_standings_archive SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                updates["limited_event_standings_archive"] = cur.rowcount

            # limited_match_records_archive
            if "limited_match_records_archive" in tables:
                count = _update_cols(cur, "limited_match_records_archive", ("winner_id", "loser_id"), new_user_id, old_user_id)
                updates["limited_match_records_archive"] = count

            # limited_arena_runs_archive
            if "limited_arena_runs_archive" in tables:
                cur.execute("UPDATE limited_arena_runs_archive SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
                updates["limited_arena_runs_archive"] = cur.rowcount

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to transfer elo.db: {e}")
            return {"success": False, "error": f"Failed during ELO transfer: {e}"}

        summary = {k: v for k, v in updates.items() if v}
        total_rows = sum(v for v in updates.values() if isinstance(v, int))

        logger.info(f"Admin transferred history from {old_user_id} to {new_user_id}: {summary}")
        return {
            "success": True,
            "message": f"Transferred history from {old_user_id} to {new_user_id} ({total_rows} rows updated)",
            "details": summary,
        }

    def rename_player(self, user_id: str, new_name: str) -> dict:
        """Rename a player's display name in all standings and match history."""
        renamed_any = False

        # Rename in bot standings
        bot_elo = self._elo_repo.get_user_elo(user_id)
        if bot_elo is not None:
            if self._elo_repo.rename_player(user_id, new_name):
                renamed_any = True
            bot_matches = self._match_repo.rename_player_in_matches(user_id, new_name)
        else:
            bot_matches = 0

        # Rename in paper standings
        paper_elo = self._elo_repo.get_user_paper_elo(str(user_id))
        if paper_elo is not None:
            if self._elo_repo.rename_paper_player(str(user_id), new_name):
                renamed_any = True

        # Rename in web match records
        web_matches = self._match_repo.rename_player_in_web_matches(str(user_id), new_name)

        if renamed_any:
            logger.info(
                f"Admin renamed player {user_id} to '{new_name}' "
                f"(bot matches: {bot_matches}, web matches: {web_matches})"
            )
            return {"success": True, "message": f"Player renamed to '{new_name}'"}

        if bot_matches + web_matches > 0:
            return {"success": True, "message": f"Player renamed in {bot_matches + web_matches} match records"}

        return {"success": False, "error": "Player not found in any standings"}
