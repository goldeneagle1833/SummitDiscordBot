"""Repository for Rumble bones, prizes, and admin management."""

import sqlite3
from webapp_config import RUMBLE_DB_PATH


class RumbleRepository:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or RUMBLE_DB_PATH)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Admins ---

    def is_rumble_admin(self, discord_user_id: str) -> bool:
        conn = self._connect()
        row = conn.execute(
            "SELECT 1 FROM rumble_admins WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()
        conn.close()
        return row is not None

    def get_admins(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT discord_user_id, display_name, added_at FROM rumble_admins ORDER BY added_at"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_admin(self, discord_user_id: str, display_name: str | None = None):
        conn = self._connect()
        conn.execute(
            "INSERT OR IGNORE INTO rumble_admins (discord_user_id, display_name) VALUES (?, ?)",
            (discord_user_id, display_name),
        )
        conn.commit()
        conn.close()

    def remove_admin(self, discord_user_id: str) -> bool:
        conn = self._connect()
        cursor = conn.execute(
            "DELETE FROM rumble_admins WHERE discord_user_id = ?",
            (discord_user_id,),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    # --- Bones ---

    def get_all_balances(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT discord_user_id, display_name, balance FROM rumble_bones ORDER BY balance DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_balance(self, discord_user_id: str) -> int:
        conn = self._connect()
        row = conn.execute(
            "SELECT balance FROM rumble_bones WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()
        conn.close()
        return row["balance"] if row else 0

    def adjust_bones(
        self, discord_user_id: str, amount: int, reason: str,
        display_name: str | None = None, admin_user_id: str | None = None,
    ) -> int:
        """Add or remove bones. Returns new balance."""
        conn = self._connect()
        # Ensure player row exists
        conn.execute(
            "INSERT OR IGNORE INTO rumble_bones (discord_user_id, display_name, balance) VALUES (?, ?, 0)",
            (discord_user_id, display_name),
        )
        if display_name:
            conn.execute(
                "UPDATE rumble_bones SET display_name = ? WHERE discord_user_id = ?",
                (display_name, discord_user_id),
            )
        conn.execute(
            "UPDATE rumble_bones SET balance = balance + ? WHERE discord_user_id = ?",
            (amount, discord_user_id),
        )
        conn.execute(
            "INSERT INTO rumble_bone_transactions (discord_user_id, amount, reason, admin_user_id) VALUES (?, ?, ?, ?)",
            (discord_user_id, amount, reason, admin_user_id),
        )
        row = conn.execute(
            "SELECT balance FROM rumble_bones WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()
        conn.commit()
        conn.close()
        return row["balance"]

    def set_bones(
        self, discord_user_id: str, amount: int, reason: str,
        display_name: str | None = None, admin_user_id: str | None = None,
    ) -> int:
        """Set bones to an exact amount. Returns new balance."""
        current = self.get_balance(discord_user_id)
        diff = amount - current
        return self.adjust_bones(discord_user_id, diff, reason, display_name, admin_user_id)

    def get_transactions(self, discord_user_id: str, limit: int = 50) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, amount, reason, admin_user_id, created_at FROM rumble_bone_transactions "
            "WHERE discord_user_id = ? ORDER BY created_at DESC LIMIT ?",
            (discord_user_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # --- Earnings Config ---

    def get_earnings_config(self) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT key, label, category, bones, sort_order FROM rumble_earnings_config ORDER BY sort_order"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def update_earning(self, key: str, bones: int) -> bool:
        conn = self._connect()
        cursor = conn.execute(
            "UPDATE rumble_earnings_config SET bones = ? WHERE key = ?",
            (bones, key),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    # --- Prizes ---

    def get_prizes(self, active_only: bool = True) -> list[dict]:
        conn = self._connect()
        query = "SELECT id, name, cost, stock, description, sort_order, active FROM rumble_prizes"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY sort_order"
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_prize(self, prize_id: int) -> dict | None:
        conn = self._connect()
        row = conn.execute(
            "SELECT id, name, cost, stock, description, sort_order, active FROM rumble_prizes WHERE id = ?",
            (prize_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_prize(self, prize_id: int, **fields) -> bool:
        allowed = {"name", "cost", "stock", "description", "sort_order", "active"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [prize_id]
        conn = self._connect()
        cursor = conn.execute(
            f"UPDATE rumble_prizes SET {set_clause} WHERE id = ?", values
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def add_prize(self, name: str, cost: int = 0, stock: int | None = None,
                  description: str | None = None, sort_order: int = 0) -> int:
        conn = self._connect()
        cursor = conn.execute(
            "INSERT INTO rumble_prizes (name, cost, stock, description, sort_order) VALUES (?, ?, ?, ?, ?)",
            (name, cost, stock, description, sort_order),
        )
        conn.commit()
        prize_id = cursor.lastrowid
        conn.close()
        return prize_id

    def delete_prize(self, prize_id: int) -> bool:
        conn = self._connect()
        cursor = conn.execute("DELETE FROM rumble_prizes WHERE id = ?", (prize_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0
