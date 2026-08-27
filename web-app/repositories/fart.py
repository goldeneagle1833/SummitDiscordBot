"""Repository for fart scores database access."""

import json
import sqlite3
from pathlib import Path
from random import randint

from webapp_config import FART_SCORES_DB_PATH

# Default effects for fart game commands (JSON-serialized)
_CMD_EFFECTS = {
    "fart": {"action": "roll", "formula": "1d100", "points": "roll_value"},
    "fart_gift": {"action": "gift_roll", "formula": "1d100", "points": "roll_value",
                  "target": "specified", "uses_daily": True,
                  "once_per_recipient_per_season": True},
    "fartprediction": {"action": "prediction", "correct_multiplier": 2, "wrong_multiplier": 0.5},
    "bullfart": {"action": "bonus", "source": "last_fart_type",
                 "bonuses": {"curio_shart": 50, "unique": 35, "elite": 25, "exceptional": 15, "ordinary": 10}},
    "taxes": {"action": "redistribute", "from": "others", "to": "leader", "percent": 20},
    "wealth": {"action": "redistribute", "from": "top5", "to": "others", "percent": 50},
}

_SHOP_EFFECTS = {
    "blue_shell": {"action": "damage", "target": "leader", "formula": "6d20/2"},
    "red_shell": {"action": "damage", "target": "ahead_1", "formula": "3d20/2"},
    "green_shell": {"action": "damage", "target": "random_ahead", "formula": "2d20/2"},
    "banana": {"action": "damage", "target": "random_behind", "formula": "2d20/2"},
    "big_banana": {"action": "damage", "target": "random_behind", "formula": "4d10"},
    "star": {"action": "protect", "duration": "72h", "cost_type": "percent", "cost_percent": 10,
             "blocked_after": "evil_star"},
    "mushroom": {"action": "buff", "effect": "double_roll", "description": "Next fart rolls twice, take higher"},
    "bobomb": {"action": "damage", "target": "top5", "formula": "3d20/2"},
    "fart_star": {"action": "remove_buff", "target": "random_protected", "removes": "star",
                  "cost_type": "percent", "cost_percent": 10, "blocked_after": "evil_star"},
    "evil_star": {"action": "conditional", "condition": "score_equals", "value": 666,
                  "on_true": {"action": "multiply_score", "multiplier": 2},
                  "cost_type": "free", "once_per_season": True,
                  "locks_star_commands": True},
    "thunder_fart": {"action": "damage", "target": "all", "amount": 10},
    "gas_shield": {"action": "shield", "reflect_percent": 50},
    "stink_bomb": {"action": "damage", "target": "random_any", "formula": "3d20/2"},
    "fart_rocket": {"action": "swap_scores", "target": "random"},
    "fart_lance": {"action": "multi_damage", "target": "ahead_3",
                   "formulas": ["3d20/2", "2d20/2", "1d20/2"]},
    "fart_trap": {"action": "trap", "target": "random", "effect": "attack_backfire"},
    "fart_twister": {"action": "launch", "target": "random",
                     "damage_formula": "target_score/2", "uses_daily": True},
    "stink_cloud": {"action": "block_shop", "target": "random", "duration": "24h",
                    "cost_type": "percent", "cost_percent": 5},
    "gas_gamble": {"action": "gamble", "win_chance": 40, "win_multiplier": 2, "lose_multiplier": 0},
    "fart_leech": {"action": "steal", "target": "random", "formula": "2d20/2"},
    "fart_donation": {"action": "donate", "target": "specified", "cost_type": "custom",
                      "max_amount": 100, "once_per_recipient_per_season": True},
    "fart_court": {"action": "court", "target": "specified", "win_chance": 50, "cost_type": "custom"},
}


class FartRepository:
    """Data access for fart_scores.db."""

    _DEFAULT_SHOP_ITEMS = [
        # (name, label, description, cost, damage, cooldown)
        ("blue_shell", "Blue Shell", "Hits the leader with 6d20/2 damage", 20, 0, "daily"),
        ("red_shell", "Red Shell", "Hits the player directly in front of you with 3d20/2 damage", 10, 0, "none"),
        ("green_shell", "Green Shell", "Hits a random player in front of you with 2d20/2 damage", 5, 0, "none"),
        ("banana", "Banana", "Hits a random player behind you with 2d20/2 damage", 5, 0, "none"),
        ("big_banana", "Big Banana", "Hits a random player behind you with 4d10 damage", 20, 0, "daily"),
        ("star", "Star", "Protects you from all items for 72 hours (costs 10% of your points). Blocked after Evil Star.", 0, 0, "weekly"),
        ("mushroom", "Mushroom", "Next fart rolls twice, take higher!", 5, 0, "weekly"),
        ("bobomb", "Bob-omb", "Hits the top 5 players with 3d20/2 damage", 25, 0, "none"),
        ("fart_star", "Fart Star", "Removes star protection from a random protected user. Blocked after Evil Star.", 0, 0, "weekly"),
        ("evil_star", "Evil Star", "Doubles your points if you have exactly 666. Once/season; locks out other stars.", 0, 0, "once_per_season"),
        ("thunder_fart", "Thunder Fart", "Hits ALL players for 10 damage each", 10, 0, "weekly"),
        ("gas_shield", "Gas Shield", "Reflects 50% damage back at the next attacker", 8, 0, "none"),
        ("stink_bomb", "Stink Bomb", "Hits a random player (anyone!) for 3d20/2 damage", 12, 0, "none"),
        ("fart_rocket", "Fart Rocket", "Swap scores with a random player", 100, 0, "weekly"),
        ("fart_lance", "Fart Lance", "Hits up to 3 players ahead with diminishing damage", 15, 0, "none"),
        ("fart_trap", "Fart Trap", "A player's next attack backfires on them!", 20, 0, "none"),
        ("fart_twister", "Fart Twister", "Launch a player into another! Damage = half launched player's score", 50, 0, "weekly"),
        ("stink_cloud", "Stink Cloud", "Blocks a random player from shop for 24 hours (5% of points)", 0, 0, "daily"),
        ("gas_gamble", "Gas Gamble", "40% chance to double your bet, 60% to lose it all", 0, 0, "none"),
        ("fart_leech", "Fart Leech", "Steal 2d20/2 points from a random player", 5, 0, "daily"),
        ("fart_donation", "Fart Donation", "Donate points to another player (max 100, once per player per season)", 0, 0, "once_per_season"),
        ("fart_court", "Fart Court", "50% chance they pay you the amount, 50% chance you pay them", 0, 0, "weekly"),
    ]

    _DEFAULT_COMMANDS = [
        ("fart", "Fart", "Roll for random fart points", 0, 0, "daily", 1),
        ("fart_gift", "Fart Gift", "Roll your daily fart and give the points to another player (once per player per season)", 0, 0, "daily", 2),
        ("fartprediction", "Fart Prediction", "Predict fart type for 2x or half points", 0, 0, "daily", 3),
        ("bullfart", "Bull Fart", "Bonus points based on last fart type", 0, 0, "weekly", 4),
        ("taxes", "Taxes", "Take 20% from everyone else, give it all to the fartlord", 0, 20, "once_per_reign", 5),
        ("wealth", "Wealth", "Take 50% from top 5, give to everyone else", 0, 50, "once_per_reign", 6),
    ]

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or FART_SCORES_DB_PATH)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _add_column_if_missing(conn, table: str, column: str, col_type: str = "TEXT"):
        """Add a column to a table if it doesn't already exist."""
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.commit()

    def _ensure_commands_table(self, conn):
        """Create fart_game_commands table and seed defaults if empty."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fart_game_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                description TEXT,
                cost INTEGER NOT NULL DEFAULT 0,
                damage INTEGER NOT NULL DEFAULT 0,
                cooldown TEXT NOT NULL DEFAULT 'daily',
                enabled INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                effect TEXT
            )
        """)
        self._add_column_if_missing(conn, "fart_game_commands", "effect", "TEXT")
        # Gothic S6: remove retired daily actions from existing installs
        conn.execute(
            "DELETE FROM fart_game_commands WHERE name IN ('attackfart', 'syphonfart')"
        )
        # Sync taxes/wealth redistribution percents on existing installs
        for name, label, desc, cost, damage, cooldown, sort_order in self._DEFAULT_COMMANDS:
            if name not in ("taxes", "wealth"):
                continue
            effect_json = json.dumps(_CMD_EFFECTS.get(name, {}))
            conn.execute(
                "UPDATE fart_game_commands SET description = ?, damage = ?, effect = ? WHERE name = ?",
                (desc, damage, effect_json, name),
            )
        count = conn.execute("SELECT COUNT(*) FROM fart_game_commands").fetchone()[0]
        if count == 0:
            for name, label, desc, cost, damage, cooldown, sort_order in self._DEFAULT_COMMANDS:
                effect_json = json.dumps(_CMD_EFFECTS.get(name, {}))
                conn.execute(
                    "INSERT INTO fart_game_commands (name, label, description, cost, damage, cooldown, sort_order, effect) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, label, desc, cost, damage, cooldown, sort_order, effect_json),
                )
            conn.commit()
        else:
            # Backfill effect for existing rows that have NULL effect
            rows = conn.execute(
                "SELECT id, name FROM fart_game_commands WHERE effect IS NULL"
            ).fetchall()
            for row in rows:
                effect = _CMD_EFFECTS.get(row["name"], {})
                conn.execute(
                    "UPDATE fart_game_commands SET effect = ? WHERE id = ?",
                    (json.dumps(effect), row["id"]),
                )
            # Ensure newer built-ins exist on older installs
            existing = {
                r["name"]
                for r in conn.execute("SELECT name FROM fart_game_commands").fetchall()
            }
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM fart_game_commands"
            ).fetchone()[0]
            for name, label, desc, cost, damage, cooldown, sort_order in self._DEFAULT_COMMANDS:
                if name in existing:
                    continue
                max_order += 1
                effect_json = json.dumps(_CMD_EFFECTS.get(name, {}))
                conn.execute(
                    "INSERT INTO fart_game_commands (name, label, description, cost, damage, cooldown, sort_order, effect) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, label, desc, cost, damage, cooldown, max_order, effect_json),
                )
            conn.commit()

    def get_leaderboard(self) -> list[dict]:
        """Get fart leaderboard data ordered by score descending."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, user_display_name, score, date_last_updated
            FROM fart_scores
            ORDER BY score DESC
        """)
        rows = cur.fetchall()
        conn.close()

        return [
            {
                "rank": rank,
                "user_id": row[0],
                "username": row[1],
                "score": row[2],
                "last_updated": row[3],
            }
            for rank, row in enumerate(rows, start=1)
        ]

    # --- Commands config ---

    def get_commands(self) -> list[dict]:
        """Get all fart game command configs."""
        conn = self._get_connection()
        self._ensure_commands_table(conn)
        rows = conn.execute(
            "SELECT id, name, label, description, cost, damage, cooldown, enabled, sort_order, effect "
            "FROM fart_game_commands ORDER BY sort_order"
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["effect"] = json.loads(d["effect"]) if d.get("effect") else {}
            results.append(d)
        return results

    def add_command(self, name: str, label: str, description: str | None = None,
                    cost: int = 0, damage: int = 0, cooldown: str = "daily",
                    effect: dict | None = None) -> int:
        """Add a new fart command config. Returns the new ID."""
        conn = self._get_connection()
        self._ensure_commands_table(conn)
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM fart_game_commands").fetchone()[0]
        effect_json = json.dumps(effect) if effect else None
        cursor = conn.execute(
            "INSERT INTO fart_game_commands (name, label, description, cost, damage, cooldown, sort_order, effect) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, label, description, cost, damage, cooldown, max_order + 1, effect_json),
        )
        conn.commit()
        command_id = cursor.lastrowid
        conn.close()
        return command_id

    def update_command(self, command_id: int, **fields) -> bool:
        """Update a fart command config. Returns True if updated."""
        allowed = {"name", "label", "description", "cost", "damage", "cooldown", "enabled", "sort_order", "effect"}
        updates = {}
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "effect" and isinstance(v, dict):
                updates[k] = json.dumps(v)
            else:
                updates[k] = v
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [command_id]
        conn = self._get_connection()
        cursor = conn.execute(f"UPDATE fart_game_commands SET {set_clause} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def delete_command(self, command_id: int) -> bool:
        """Delete a fart command config."""
        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM fart_game_commands WHERE id = ?", (command_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    # --- Shop items ---

    def _ensure_shop_table(self, conn):
        """Create fart_shop_items table and seed defaults if empty."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fart_shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                description TEXT,
                cost INTEGER NOT NULL DEFAULT 0,
                damage INTEGER NOT NULL DEFAULT 0,
                cooldown TEXT NOT NULL DEFAULT 'none',
                enabled INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                effect TEXT
            )
        """)
        self._add_column_if_missing(conn, "fart_shop_items", "effect", "TEXT")
        # Gothic S6: remove retired shop items from existing installs
        conn.execute(
            "DELETE FROM fart_shop_items WHERE name IN ('bluestar', 'blue_star')"
        )
        count = conn.execute("SELECT COUNT(*) FROM fart_shop_items").fetchone()[0]
        if count == 0:
            for i, (name, label, desc, cost, damage, cooldown) in enumerate(self._DEFAULT_SHOP_ITEMS):
                effect_json = json.dumps(_SHOP_EFFECTS.get(name, {}))
                conn.execute(
                    "INSERT INTO fart_shop_items (name, label, description, cost, damage, cooldown, sort_order, effect) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, label, desc, cost, damage, cooldown, i + 1, effect_json),
                )
            conn.commit()
        else:
            # Backfill effect for existing rows that have NULL effect
            rows = conn.execute(
                "SELECT id, name FROM fart_shop_items WHERE effect IS NULL"
            ).fetchall()
            for row in rows:
                effect = _SHOP_EFFECTS.get(row["name"], {})
                conn.execute(
                    "UPDATE fart_shop_items SET effect = ? WHERE id = ?",
                    (json.dumps(effect), row["id"]),
                )
            # Ensure newer built-ins exist (e.g. restored fart_donation)
            existing = {
                r["name"]
                for r in conn.execute("SELECT name FROM fart_shop_items").fetchall()
            }
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM fart_shop_items"
            ).fetchone()[0]
            for name, label, desc, cost, damage, cooldown in self._DEFAULT_SHOP_ITEMS:
                if name in existing:
                    continue
                max_order += 1
                effect_json = json.dumps(_SHOP_EFFECTS.get(name, {}))
                conn.execute(
                    "INSERT INTO fart_shop_items (name, label, description, cost, damage, cooldown, sort_order, effect) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, label, desc, cost, damage, cooldown, max_order, effect_json),
                )
            conn.commit()

    def get_shop_items(self) -> list[dict]:
        """Get all fart shop item configs."""
        conn = self._get_connection()
        self._ensure_shop_table(conn)
        rows = conn.execute(
            "SELECT id, name, label, description, cost, damage, cooldown, enabled, sort_order, effect "
            "FROM fart_shop_items ORDER BY sort_order"
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["effect"] = json.loads(d["effect"]) if d.get("effect") else {}
            results.append(d)
        return results

    def add_shop_item(self, name: str, label: str, description: str | None = None,
                      cost: int = 0, damage: int = 0, cooldown: str = "none",
                      effect: dict | None = None) -> int:
        """Add a new fart shop item. Returns the new ID."""
        conn = self._get_connection()
        self._ensure_shop_table(conn)
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM fart_shop_items").fetchone()[0]
        effect_json = json.dumps(effect) if effect else None
        cursor = conn.execute(
            "INSERT INTO fart_shop_items (name, label, description, cost, damage, cooldown, sort_order, effect) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, label, description, cost, damage, cooldown, max_order + 1, effect_json),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()
        return item_id

    def update_shop_item(self, item_id: int, **fields) -> bool:
        """Update a fart shop item. Returns True if updated."""
        allowed = {"name", "label", "description", "cost", "damage", "cooldown", "enabled", "sort_order", "effect"}
        updates = {}
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "effect" and isinstance(v, dict):
                updates[k] = json.dumps(v)
            else:
                updates[k] = v
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item_id]
        conn = self._get_connection()
        cursor = conn.execute(f"UPDATE fart_shop_items SET {set_clause} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def delete_shop_item(self, item_id: int) -> bool:
        """Delete a fart shop item."""
        conn = self._get_connection()
        cursor = conn.execute("DELETE FROM fart_shop_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    # --- Game management ---

    # Never wipe on season reset: admin config + permanent one-time flags.
    _PRESERVE_ON_RESET = frozenset({
        "fart_game_commands",
        "fart_shop_items",
        # First Curio ever → 40/40/20 lava/frost/Yourt; then 10% lava/frost + 5% Yourt forever
        "uber_rare_curio_claimed",
    })

    # Known gameplay / tracking tables (documentation + test coverage).
    # reset_game() also dynamically clears ANY other non-config table so
    # newly added daily/weekly/season/reign trackers cannot be missed.
    _KNOWN_TRACKING_TABLES = frozenset({
        "fart_scores",
        "fart_history",
        "command_usage",          # !bullfart, shop daily/weekly items, !fart_court, etc.
        "lucky_charms",           # active !mushroom buff
        "lucky_charm_usage",      # !mushroom once/week
        "fart_leader_only_once",  # !taxes / !wealth once/reign
        "evil_star_usage",        # once/season + star locks
        "fart_donation_usage",    # once/recipient/season
        "fart_gift_usage",        # once/recipient/season
        "protection_status",      # !star 72h
        "shop_blocks",            # !stink_cloud 24h
        "gas_shields",
        "fart_traps",
        "frost_shart_freeze",     # Frostshart: shop + specials blocked for 24h (!fart ok)
        "uber_rare_curio_season", # lavashart/frostshart once each per player per season
        "yourt_rampage",          # 1-hour Yourt shop-chaos window + attack ticker
    })

    @staticmethod
    def _is_safe_table_name(name: str) -> bool:
        """Only allow simple SQLite identifiers (blocks injection via odd names)."""
        return bool(name) and name.replace("_", "").isalnum() and not name[0].isdigit()

    def reset_game(self) -> dict:
        """Full season reset — wipe ALL gameplay and tracking state.

        Clears every table in fart_scores.db except preserved tables
        (fart_game_commands, fart_shop_items, uber_rare_curio_claimed).
        Uses dynamic discovery so daily / weekly / season / reign cooldowns,
        item usage, gifts, donations, protections, per-player uber-rare
        once-per-season flags, and any future trackers are all cleared.
        The one-time global uber-rare Curio flag is intentionally kept.
        """
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        cleared = {}
        for row in rows:
            table = row[0] if not isinstance(row, sqlite3.Row) else row["name"]
            if table in self._PRESERVE_ON_RESET:
                continue
            if not self._is_safe_table_name(table):
                continue
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            conn.execute(f'DELETE FROM "{table}"')
            cleared[table] = count
        # Reset AUTOINCREMENT counters for wiped tables (ignore if unused)
        try:
            conn.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
        return cleared

    EVIL_START_SCORE_MIN = -250
    EVIL_START_SCORE_MAX = 250

    def evil_start(self) -> dict:
        """Evil start - same as reset_game, then random starting scores (-250 to 250)."""
        conn = self._get_connection()
        # Gather known players before reset
        try:
            players = conn.execute(
                "SELECT user_id, user_display_name FROM fart_scores"
            ).fetchall()
            players = [(r[0], r[1]) for r in players]
        except sqlite3.OperationalError:
            players = []
        conn.close()

        # Reset everything first (same as the red Reset Fart Game button)
        self.reset_game()

        if not players:
            return {"players_affected": 0, "message": "No players found - game reset only"}

        # Re-seed with chaotic scores
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fart_scores (
                user_id INTEGER PRIMARY KEY,
                user_display_name TEXT,
                date_last_updated TEXT,
                score INTEGER
            )
        """)
        results = []
        for user_id, display_name in players:
            score = randint(self.EVIL_START_SCORE_MIN, self.EVIL_START_SCORE_MAX)
            conn.execute(
                "INSERT INTO fart_scores (user_id, user_display_name, date_last_updated, score) VALUES (?, ?, NULL, ?)",
                (user_id, display_name, score),
            )
            results.append({"user_id": user_id, "username": display_name, "score": score})
        conn.commit()
        conn.close()
        return {"players_affected": len(results), "players": results}
