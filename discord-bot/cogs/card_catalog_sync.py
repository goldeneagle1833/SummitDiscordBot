"""Card Catalog Sync cog — daily sync of card data from the Sorcery TCG API."""

import asyncio
import datetime
import json
import logging
import sqlite3
from zoneinfo import ZoneInfo

import discord
import requests
from discord.ext import commands, tasks

import config

logger = logging.getLogger("discord_bot")

EST = ZoneInfo("America/New_York")

SORCERY_API_URL = "https://api.sorcerytcg.com/api/cards"


class CardCatalogSyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.card_sync_task.start()

    def cog_unload(self):
        self.card_sync_task.cancel()

    @tasks.loop(time=datetime.time(hour=6, minute=0, tzinfo=EST))
    async def card_sync_task(self):
        """Run daily at 6:00 AM EST."""
        logger.info("Card catalog sync task firing...")
        try:
            result = await asyncio.to_thread(self._sync_cards)
            if result and result["has_changes"]:
                await self._notify_changes(result)
        except Exception:
            logger.error("Card catalog sync failed", exc_info=True)

    @card_sync_task.before_loop
    async def before_card_sync(self):
        await self.bot.wait_until_ready()
        next_run = self.card_sync_task.next_iteration
        logger.info(f"Card catalog sync task is ready - next run: {next_run}")

    @commands.command(name="sync_cards")
    @commands.has_permissions(administrator=True)
    async def trigger_sync(self, ctx):
        """Manually trigger a card catalog sync (admin only)."""
        msg = await ctx.send("Syncing card catalog from Sorcery TCG API...")
        try:
            result = await asyncio.to_thread(self._sync_cards)
            if result is None:
                await msg.edit(content="Sync failed - check logs.")
                return
            if result["has_changes"]:
                await msg.edit(content=(
                    f"Sync complete! "
                    f"+{result['added']} added, "
                    f"~{result['updated']} updated, "
                    f"-{result['removed']} removed. "
                    f"Total: {result['total']}"
                ))
                await self._notify_changes(result)
            else:
                await msg.edit(content=f"Sync complete - no changes. Total: {result['total']} cards.")
        except Exception as e:
            logger.error(f"Manual card sync failed: {e}", exc_info=True)
            await msg.edit(content=f"Sync failed: {e}")

    def _sync_cards(self) -> dict | None:
        """Fetch cards from API and sync to DB. Returns result dict or None on failure."""
        # Fetch from API
        try:
            response = requests.get(SORCERY_API_URL, timeout=30, headers={"accept": "*/*"})
            response.raise_for_status()
            api_cards = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch cards from Sorcery API: {e}")
            return None

        if not isinstance(api_cards, list) or len(api_cards) == 0:
            logger.error(f"Unexpected API response: not a list or empty")
            return None

        logger.info(f"Fetched {len(api_cards)} cards from Sorcery TCG API")

        # Sync to DB
        conn = sqlite3.connect("elo.db")
        conn.row_factory = sqlite3.Row

        added_cards = []
        updated_cards = []

        api_names = set()
        for card_data in api_cards:
            name = card_data.get("name", "").strip()
            if not name:
                continue
            api_names.add(name)

            guardian = card_data.get("guardian", {})
            thresholds = guardian.get("thresholds", {})
            raw_json = json.dumps(card_data, ensure_ascii=False, sort_keys=True)

            existing = conn.execute(
                "SELECT raw_json FROM card_catalog WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()

            if existing:
                if existing["raw_json"] != raw_json:
                    conn.execute(
                        "UPDATE card_catalog SET card_type=?, rarity=?, elements=?, sub_types=?, "
                        "cost=?, attack=?, defence=?, life=?, threshold_air=?, threshold_earth=?, "
                        "threshold_fire=?, threshold_water=?, rules_text=?, sets_json=?, raw_json=?, "
                        "updated_at=strftime('%Y-%m-%d %H:%M:%S', 'now') "
                        "WHERE name = ? COLLATE NOCASE",
                        (
                            guardian.get("type", ""),
                            guardian.get("rarity", ""),
                            card_data.get("elements", ""),
                            card_data.get("subTypes", ""),
                            guardian.get("cost"),
                            guardian.get("attack"),
                            guardian.get("defence"),
                            guardian.get("life"),
                            thresholds.get("air", 0),
                            thresholds.get("earth", 0),
                            thresholds.get("fire", 0),
                            thresholds.get("water", 0),
                            guardian.get("rulesText", ""),
                            json.dumps(card_data.get("sets", []), ensure_ascii=False),
                            raw_json,
                            name,
                        ),
                    )
                    updated_cards.append(name)
            else:
                conn.execute(
                    "INSERT INTO card_catalog (name, card_type, rarity, elements, sub_types, "
                    "cost, attack, defence, life, threshold_air, threshold_earth, "
                    "threshold_fire, threshold_water, rules_text, sets_json, raw_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        name,
                        guardian.get("type", ""),
                        guardian.get("rarity", ""),
                        card_data.get("elements", ""),
                        card_data.get("subTypes", ""),
                        guardian.get("cost"),
                        guardian.get("attack"),
                        guardian.get("defence"),
                        guardian.get("life"),
                        thresholds.get("air", 0),
                        thresholds.get("earth", 0),
                        thresholds.get("fire", 0),
                        thresholds.get("water", 0),
                        guardian.get("rulesText", ""),
                        json.dumps(card_data.get("sets", []), ensure_ascii=False),
                        raw_json,
                    ),
                )
                added_cards.append(name)

        # Remove cards no longer in API
        all_db = conn.execute("SELECT name FROM card_catalog").fetchall()
        db_names = {r["name"] for r in all_db}
        api_names_lower = {n.lower() for n in api_names}
        removed_cards = [n for n in db_names if n.lower() not in api_names_lower]

        for name in removed_cards:
            conn.execute("DELETE FROM card_catalog WHERE name = ?", (name,))

        conn.commit()

        # Get total count
        total = conn.execute("SELECT COUNT(*) FROM card_catalog").fetchone()[0]

        # Log sync
        conn.execute(
            "INSERT INTO card_catalog_sync_log (cards_added, cards_updated, cards_removed, total_cards) "
            "VALUES (?, ?, ?, ?)",
            (len(added_cards), len(updated_cards), len(removed_cards), total),
        )
        conn.commit()
        conn.close()

        has_changes = len(added_cards) > 0 or len(updated_cards) > 0 or len(removed_cards) > 0

        logger.info(
            f"Card sync complete: +{len(added_cards)} added, "
            f"~{len(updated_cards)} updated, -{len(removed_cards)} removed. "
            f"Total: {total}"
        )

        return {
            "added": len(added_cards),
            "updated": len(updated_cards),
            "removed": len(removed_cards),
            "total": total,
            "added_cards": added_cards,
            "updated_cards": updated_cards,
            "removed_cards": removed_cards,
            "has_changes": has_changes,
        }

    async def _notify_changes(self, result: dict):
        """DM the bot owner with sync changes."""
        owner_id = config.OWNER_ID
        if not owner_id:
            logger.warning("No OWNER_ID configured, skipping card sync DM")
            return

        try:
            owner = await self.bot.fetch_user(owner_id)
        except Exception as e:
            logger.error(f"Could not fetch owner user {owner_id}: {e}")
            return

        embed = discord.Embed(
            title="Card Catalog Sync",
            color=0x00CC66,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Sorcery TCG API Sync")

        summary = (
            f"**+{result['added']}** added, "
            f"**{result['updated']}** updated, "
            f"**{result['removed']}** removed\n"
            f"**{result['total']}** total cards"
        )
        embed.add_field(name="Summary", value=summary, inline=False)

        if result["added_cards"]:
            names = ", ".join(result["added_cards"][:25])
            if len(result["added_cards"]) > 25:
                names += f" ... and {len(result['added_cards']) - 25} more"
            embed.add_field(name="New Cards", value=names, inline=False)

        if result["updated_cards"]:
            names = ", ".join(result["updated_cards"][:25])
            if len(result["updated_cards"]) > 25:
                names += f" ... and {len(result['updated_cards']) - 25} more"
            embed.add_field(name="Updated Cards", value=names, inline=False)

        if result["removed_cards"]:
            names = ", ".join(result["removed_cards"][:25])
            if len(result["removed_cards"]) > 25:
                names += f" ... and {len(result['removed_cards']) - 25} more"
            embed.add_field(name="Removed Cards", value=names, inline=False)

        try:
            await owner.send(embed=embed)
            logger.info(f"Card sync DM sent to owner {owner_id}")
        except discord.Forbidden:
            logger.warning(f"Cannot DM owner {owner_id} - DMs disabled")
        except Exception as e:
            logger.error(f"Failed to DM owner: {e}")


def ensure_card_catalog_table():
    """Create card_catalog tables if they don't exist (called from main.py)."""
    conn = sqlite3.connect("elo.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            card_type TEXT NOT NULL DEFAULT '',
            rarity TEXT NOT NULL DEFAULT '',
            elements TEXT NOT NULL DEFAULT '',
            sub_types TEXT NOT NULL DEFAULT '',
            cost INTEGER,
            attack INTEGER,
            defence INTEGER,
            life INTEGER,
            threshold_air INTEGER NOT NULL DEFAULT 0,
            threshold_earth INTEGER NOT NULL DEFAULT 0,
            threshold_fire INTEGER NOT NULL DEFAULT 0,
            threshold_water INTEGER NOT NULL DEFAULT 0,
            rules_text TEXT NOT NULL DEFAULT '',
            sets_json TEXT NOT NULL DEFAULT '[]',
            raw_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS card_catalog_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            cards_added INTEGER NOT NULL DEFAULT 0,
            cards_updated INTEGER NOT NULL DEFAULT 0,
            cards_removed INTEGER NOT NULL DEFAULT 0,
            total_cards INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


async def setup(bot):
    await bot.add_cog(CardCatalogSyncCog(bot))
