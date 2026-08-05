import asyncio
import logging
import sqlite3

import discord
from discord.ext import commands

import config

logger = logging.getLogger("discord_bot")

# Hardcoded fallback used to seed the database on first run.
_SEED_DATA = {
    # channel_id, message_id, label, mappings: [(emoji, emoji_id, role_id, role_name)]
    "1516071350463238185": [
        {
            "message_id": "1516072276955500666",
            "label": "Role Assignment Part 1",
            "mappings": [
                ("\U0001f9d9\u200d\u2642\ufe0f", None, "1511379240967340124", "Archimago Cabal"),
                ("\U0001f30a", None, "1511379741372841994", "Waveshaper Cove"),
                ("\U0001f32c\ufe0f", None, "1511382886584942592", "AoA Castle"),
                ("\U0001faa8", None, "1511386474770075669", "AoE Its Earth or Nothin"),
                ("\u2764\ufe0f\u200d\U0001f525", None, "1519310101612073170", "AoF is playable"),
                ("\U0001f4a7", None, "1519310372270637066", "AoW isn't playable"),
                ("\U0001f3ad", None, "1511387392827719960", "Imposter Syndrome"),
                ("\U0001f9dd\u200d\u2640\ufe0f", None, "1511400913431171152", "Enchantress' Grotto"),
                ("\U0001f43b", None, "1511415969275183255", "Bruin Brewers"),
                ("\U0001f47b", None, "1511417944209621184", "Harbingers Void"),
                ("\U0001f30e", None, "1513872795615105117", "Geo's Cave of Rubble"),
                ("\U0001f9b6", None, "1514246397380264096", "Pathfinder Playhouse"),
                ("\U0001f308", None, "1515890413830017154", "Rainbow Elementists"),
                ("\u2696\ufe0f", None, "1517147559657869463", "Percy's Tribunal"),
                ("HATE", "1465805496672845996", "1519311141434687578", "Sorcerers!!"),
                ("\u2694\ufe0f", None, "1517185101379670107", "Bae Blades"),
                ("\U0001f4a3", None, "1519171038271770798", "Realmeater"),
                ("\U0001f525", None, "1519310835506348073", "Flamecaller"),
                ("\U0001f6e1\ufe0f", None, "1519310876497285271", "IronSkin"),
            ],
        },
        {
            "message_id": "1519313869192040448",
            "label": "Role Assignment Part 2",
            "mappings": [
                ("\U0001f40a", None, "1519310626051195021", "Interrogator"),
                ("\U0001f608", None, "1519314520407933079", "Corruptor"),
                ("\U0001f93a", None, "1519310450188222544", "BattleAvatar"),
                ("\U0001f480", None, "1519311086333988945", "Necro's War crimes"),
                ("\u26a1", None, "1519311188247445597", "Sparky"),
                ("\U0001f409", None, "1519310581285261412", "There be Dragonlords"),
                ("\u269c\ufe0f", None, "1519311410780311563", "Templar Knights"),
                ("\U0001f31f", None, "1519336849771069662", "Our Lord and Savior"),
                ("\U0001fa84", None, "1519311335882625215", "God Tier Magician"),
                ("\U0001f494", None, "1519339702405042308", "An a Bliss"),
                ("\U0001f9d9\u200d\u2640\ufe0f", None, "1519311233403191397", "Witch's Cauldron"),
                ("\u2620\ufe0f", None, "1519310529821147317", "Deathspeaker"),
                ("\U0001f441\ufe0f", None, "1519310943807602809", "All Seeing Eye"),
                ("\U0001f5ff", None, "1531494904881221772", "The One True Slinger"),
            ],
        },
    ],
}

DB_PATH = "match_records.db"


def _ensure_tables():
    """Create reaction role tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS reaction_role_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        );
        CREATE TABLE IF NOT EXISTS reaction_role_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL,
            emoji TEXT NOT NULL,
            emoji_id TEXT,
            role_id TEXT NOT NULL,
            role_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            UNIQUE(message_id, emoji)
        );
    """)
    conn.commit()
    conn.close()


def _seed_if_empty():
    """Seed the database with hardcoded mappings if the tables are empty."""
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM reaction_role_messages").fetchone()[0]
    if count > 0:
        conn.close()
        return
    logger.info("ReactionRoles: seeding database with default mappings")
    for channel_id, messages in _SEED_DATA.items():
        for msg in messages:
            conn.execute(
                "INSERT OR IGNORE INTO reaction_role_messages (channel_id, message_id, label) VALUES (?, ?, ?)",
                (channel_id, msg["message_id"], msg["label"]),
            )
            for emoji, emoji_id, role_id, role_name in msg["mappings"]:
                conn.execute(
                    "INSERT OR IGNORE INTO reaction_role_mappings "
                    "(message_id, emoji, emoji_id, role_id, role_name) VALUES (?, ?, ?, ?, ?)",
                    (msg["message_id"], emoji, emoji_id, role_id, role_name),
                )
    conn.commit()
    conn.close()
    logger.info("ReactionRoles: seed complete")


def _load_role_map() -> dict[int, dict]:
    """Load {int_message_id: {emoji_key: int_role_id}} from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT message_id, emoji, emoji_id, role_id FROM reaction_role_mappings"
    ).fetchall()
    conn.close()

    role_map: dict[int, dict] = {}
    for r in rows:
        mid = int(r["message_id"])
        if mid not in role_map:
            role_map[mid] = {}
        if r["emoji_id"]:
            key = int(r["emoji_id"])
        else:
            key = r["emoji"]
        role_map[mid][key] = int(r["role_id"])
    return role_map


def _load_channel_map() -> dict[int, int]:
    """Load {int_message_id: int_channel_id} from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT message_id, channel_id FROM reaction_role_messages"
    ).fetchall()
    conn.close()
    return {int(r["message_id"]): int(r["channel_id"]) for r in rows}


def _emoji_key(emoji: discord.PartialEmoji) -> object:
    """Return the lookup key for an emoji (custom ID or unicode str)."""
    if emoji.id:
        return emoji.id
    return emoji.name


class ReactionRolesCog(commands.Cog):
    """Assigns roles based on emoji reactions on specific messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _ensure_tables()
        _seed_if_empty()
        self._role_map = _load_role_map()
        self._channel_map = _load_channel_map()

    def _reload(self):
        """Reload mappings from database."""
        self._role_map = _load_role_map()
        self._channel_map = _load_channel_map()

    # ------------------------------------------------------------------
    # Startup sync
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        self._reload()
        await self._sync_reaction_roles()

    async def _sync_reaction_roles(self):
        guild = self.bot.get_guild(config.GUILD_ID)
        if guild is None:
            logger.warning("ReactionRoles: guild %s not found, skipping sync", config.GUILD_ID)
            return

        for message_id, emoji_roles in self._role_map.items():
            channel_id = self._channel_map.get(message_id)
            if channel_id is None:
                continue

            channel = guild.get_channel(channel_id)
            if channel is None:
                logger.warning("ReactionRoles: channel %s not found, skipping", channel_id)
                continue

            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                logger.warning("ReactionRoles: message %s not found, skipping", message_id)
                continue
            except discord.Forbidden:
                logger.warning("ReactionRoles: no permission to fetch message %s", message_id)
                continue

            # Build {role_id: set(user_ids)} from reactions
            reacted_users_by_role: dict[int, set[int]] = {rid: set() for rid in emoji_roles.values()}

            for reaction in message.reactions:
                key = reaction.emoji if isinstance(reaction.emoji, str) else (reaction.emoji.id or reaction.emoji.name)
                role_id = emoji_roles.get(key)
                if role_id is None:
                    continue
                async for user in reaction.users():
                    if not user.bot:
                        reacted_users_by_role[role_id].add(user.id)

            # Sync each role
            for role_id, user_ids in reacted_users_by_role.items():
                role = guild.get_role(role_id)
                if role is None:
                    logger.warning("ReactionRoles: role %s not found, skipping", role_id)
                    continue

                for uid in user_ids:
                    member = guild.get_member(uid)
                    if member and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Reaction role sync")
                            logger.info("ReactionRoles sync: added %s to %s", role.name, member)
                        except discord.Forbidden:
                            logger.warning("ReactionRoles sync: cannot add %s to %s", role.name, member)
                        await asyncio.sleep(0.5)

                for member in role.members:
                    if member.bot:
                        continue
                    if member.id not in user_ids:
                        try:
                            await member.remove_roles(role, reason="Reaction role sync (no reaction)")
                            logger.info("ReactionRoles sync: removed %s from %s", role.name, member)
                        except discord.Forbidden:
                            logger.warning("ReactionRoles sync: cannot remove %s from %s", role.name, member)
                        await asyncio.sleep(0.5)

        logger.info("ReactionRoles: startup sync complete")

    # ------------------------------------------------------------------
    # Live reaction handlers
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return

        emoji_roles = self._role_map.get(payload.message_id)
        if emoji_roles is None:
            return

        role_id = emoji_roles.get(_emoji_key(payload.emoji))
        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(role_id)
        if role is None:
            return

        member = payload.member or await guild.fetch_member(payload.user_id)
        if member.bot:
            return

        await member.add_roles(role, reason="Reaction role")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return

        emoji_roles = self._role_map.get(payload.message_id)
        if emoji_roles is None:
            return

        role_id = emoji_roles.get(_emoji_key(payload.emoji))
        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        role = guild.get_role(role_id)
        if role is None:
            return

        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        if member.bot:
            return

        await member.remove_roles(role, reason="Reaction role removed")


def setup(bot: commands.Bot):
    bot.add_cog(ReactionRolesCog(bot))
