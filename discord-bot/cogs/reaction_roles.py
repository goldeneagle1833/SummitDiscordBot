import asyncio
import logging
import sqlite3

import discord
from discord.ext import commands, tasks

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
        CREATE TABLE IF NOT EXISTS reaction_role_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            message_id TEXT,
            channel_id TEXT,
            post_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        );
        CREATE TABLE IF NOT EXISTS reaction_role_guild_roles (
            role_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            color INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL DEFAULT 0,
            assignable INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        );
        CREATE TABLE IF NOT EXISTS reaction_role_guild_emojis (
            emoji_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            animated INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        );
        CREATE TABLE IF NOT EXISTS reaction_role_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            message_id TEXT,
            error TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
        );
    """)
    # Columns for messages the bot posted itself (title/body it keeps updated).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(reaction_role_messages)")}
    for name, ddl in (
        ("title", "TEXT NOT NULL DEFAULT ''"),
        ("body", "TEXT NOT NULL DEFAULT ''"),
        ("managed", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE reaction_role_messages ADD COLUMN {name} {ddl}")
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


def _load_managed_ids() -> set[int]:
    """Message IDs the bot posted itself (their role list shows member counts)."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT message_id FROM reaction_role_messages WHERE managed = 1"
    ).fetchall()
    conn.close()
    return {int(r[0]) for r in rows}


def save_guild_snapshot(guild: discord.Guild):
    """Store the server's roles and custom emojis so the admin page can list them."""
    roles = [
        (str(r.id), r.name, r.color.value, r.position, 1 if r.is_assignable() else 0)
        for r in guild.roles if not r.is_default()
    ]
    emojis = [(str(e.id), e.name, 1 if e.animated else 0) for e in guild.emojis]
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM reaction_role_guild_roles")
        conn.executemany(
            "INSERT INTO reaction_role_guild_roles (role_id, name, color, position, assignable) "
            "VALUES (?, ?, ?, ?, ?)",
            roles,
        )
        conn.execute("DELETE FROM reaction_role_guild_emojis")
        conn.executemany(
            "INSERT INTO reaction_role_guild_emojis (emoji_id, name, animated) VALUES (?, ?, ?)",
            emojis,
        )
        conn.commit()
    finally:
        conn.close()


def _take_queue() -> list[dict]:
    """Return and remove all jobs the web app has queued for the bot."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM reaction_role_queue ORDER BY id"
        ).fetchall()]
        if rows:
            conn.execute(
                "DELETE FROM reaction_role_queue WHERE id <= ?", (rows[-1]["id"],)
            )
            conn.commit()
        return rows
    finally:
        conn.close()


def _get_post(post_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM reaction_role_posts WHERE id = ?", (post_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _finish_post(post: dict, message_id: int | None, error: str | None = None):
    """Record the outcome of a post; on success, start tracking the new message."""
    conn = sqlite3.connect(DB_PATH)
    if message_id is None:
        conn.execute(
            "UPDATE reaction_role_posts SET status = 'failed', error = ? WHERE id = ?",
            (error, post["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO reaction_role_messages "
            "(channel_id, message_id, label, title, body, managed) VALUES (?, ?, ?, ?, ?, 1)",
            (post["channel_id"], str(message_id), post["title"], post["title"], post["body"]),
        )
        conn.execute(
            "UPDATE reaction_role_posts SET status = 'posted', message_id = ?, error = NULL "
            "WHERE id = ?",
            (str(message_id), post["id"]),
        )
    conn.commit()
    conn.close()


def _get_message_row(message_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM reaction_role_messages WHERE message_id = ?", (str(message_id),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _get_mapping_rows(message_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT emoji, emoji_id, role_id, role_name FROM reaction_role_mappings "
        "WHERE message_id = ? ORDER BY id",
        (str(message_id),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _emoji_text(mapping: dict) -> str:
    """Emoji as it should appear in message text / be added as a reaction."""
    if mapping["emoji_id"]:
        return f"<:{mapping['emoji']}:{mapping['emoji_id']}>"
    return mapping["emoji"]


def build_role_embed(
    title: str, body: str, mappings: list[dict], counts: dict[int, int] | None = None,
) -> discord.Embed:
    """Embed for a bot-posted role message: title, text, then one line per role.

    counts maps role_id -> members holding the role (shown after each role).
    """
    counts = counts or {}
    lines = []
    for m in mappings:
        line = f"{_emoji_text(m)}  <@&{m['role_id']}>"
        count = counts.get(int(m["role_id"]))
        if count is not None:
            line += f" · {count} member{'' if count == 1 else 's'}"
        lines.append(line)
    parts = [p for p in (body, "\n".join(lines)) if p]
    if not lines:
        parts.append("*Roles coming soon.*")
    embed = discord.Embed(
        title=title[:256],
        description="\n\n".join(parts)[:4096],
        color=discord.Color.gold(),
    )
    embed.set_footer(text="React to get a role. Remove your reaction to drop it.")
    return embed


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
        self._managed = _load_managed_ids()
        # Bot posts whose member counts need refreshing (done by _process_queue).
        self._dirty_posts: set[int] = set()

    def _reload(self):
        """Reload mappings from database."""
        self._role_map = _load_role_map()
        self._channel_map = _load_channel_map()
        self._managed = _load_managed_ids()

    def cog_unload(self):
        self._refresh_mappings.cancel()
        self._process_queue.cancel()

    @tasks.loop(minutes=5)
    async def _refresh_mappings(self):
        """Periodic reload, a fallback in case a queued change was missed."""
        self._reload()
        logger.debug("ReactionRoles: refreshed mappings from database")

    @tasks.loop(seconds=5)
    async def _process_queue(self):
        """Apply admin-page changes (queued by the web app) within seconds."""
        try:
            jobs = _take_queue()
        except sqlite3.Error:
            logger.exception("ReactionRoles: could not read job queue")
            return
        if not jobs and not self._dirty_posts:
            return
        if jobs:
            self._reload()
        guild = self.bot.get_guild(config.GUILD_ID)
        if guild is None:
            logger.warning("ReactionRoles: guild %s not found, dropping %d jobs", config.GUILD_ID, len(jobs))
            return

        synced: set[int] = set()
        for job in jobs:
            try:
                action = job["action"]
                if action == "post":
                    message_id = await self._publish_post(guild, job["post_id"])
                    if message_id:
                        self._reload()
                        await self._sync_message(guild, message_id)
                        synced.add(message_id)
                elif action == "sync":
                    message_id = int(job["message_id"])
                    if message_id not in synced:
                        await self._sync_message(guild, message_id)
                        synced.add(message_id)
                elif action == "clear":
                    await self._clear_own_reactions(guild, int(job["channel_id"]), int(job["message_id"]))
                elif action == "delete_post":
                    await self._delete_post(guild, int(job["channel_id"]), int(job["message_id"]))
                elif action == "refresh_roles":
                    save_guild_snapshot(guild)
            except Exception:
                logger.exception("ReactionRoles: job %s failed", job)

        # Member counts changed since the last pass (roles added/removed anywhere).
        dirty, self._dirty_posts = self._dirty_posts - synced, set()
        for message_id in dirty:
            try:
                await self._refresh_post(guild, message_id)
            except Exception:
                logger.exception("ReactionRoles: could not refresh counts on %s", message_id)

    @_process_queue.before_loop
    async def _before_process_queue(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Startup sync
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        self._reload()
        if not self._refresh_mappings.is_running():
            self._refresh_mappings.start()
        if not self._process_queue.is_running():
            self._process_queue.start()
        self._save_snapshot()
        await self._sync_reaction_roles()

    # ------------------------------------------------------------------
    # Role / emoji list for the admin page
    # ------------------------------------------------------------------
    def _save_snapshot(self):
        guild = self.bot.get_guild(config.GUILD_ID)
        if guild is None:
            return
        try:
            save_guild_snapshot(guild)
        except sqlite3.Error:
            logger.exception("ReactionRoles: could not save role list")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        if role.guild.id == config.GUILD_ID:
            self._save_snapshot()

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if role.guild.id == config.GUILD_ID:
            self._save_snapshot()

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if after.guild.id == config.GUILD_ID:
            self._save_snapshot()

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        if guild.id == config.GUILD_ID:
            self._save_snapshot()

    async def _sync_reaction_roles(self):
        guild = self.bot.get_guild(config.GUILD_ID)
        if guild is None:
            logger.warning("ReactionRoles: guild %s not found, skipping sync", config.GUILD_ID)
            return

        for message_id in list(self._role_map):
            await self._backfill_roles(guild, message_id)

        logger.info("ReactionRoles: startup sync complete")

    async def _fetch_message(self, guild: discord.Guild, channel_id: int, message_id: int):
        channel = guild.get_channel(channel_id)
        if channel is None:
            logger.warning("ReactionRoles: channel %s not found, skipping", channel_id)
            return None
        try:
            return await channel.fetch_message(message_id)
        except discord.NotFound:
            logger.warning("ReactionRoles: message %s not found, skipping", message_id)
        except discord.Forbidden:
            logger.warning("ReactionRoles: no permission to fetch message %s", message_id)
        return None

    async def _sync_message(self, guild: discord.Guild, message_id: int):
        """Bring one message in line with its mappings: text, bot reactions, roles."""
        row = _get_message_row(message_id)
        if row is None:
            return
        message = await self._fetch_message(guild, int(row["channel_id"]), message_id)
        if message is None:
            return
        mappings = _get_mapping_rows(message_id)

        if row["managed"]:
            await self._update_post_embed(guild, message, row, mappings)

        # The bot reacts with every mapped emoji so members have something to click,
        # and takes back its own reaction for emojis that are no longer mapped.
        wanted = {int(m["emoji_id"]) if m["emoji_id"] else m["emoji"]: m for m in mappings}
        for reaction in message.reactions:
            key = reaction.emoji if isinstance(reaction.emoji, str) else (reaction.emoji.id or reaction.emoji.name)
            if reaction.me and key not in wanted:
                try:
                    await message.remove_reaction(reaction.emoji, self.bot.user)
                except discord.HTTPException:
                    logger.warning("ReactionRoles: could not remove %s from %s", key, message_id)
        have = {
            (r.emoji if isinstance(r.emoji, str) else (r.emoji.id or r.emoji.name))
            for r in message.reactions if r.me
        }
        for key, m in wanted.items():
            if key in have:
                continue
            try:
                await message.add_reaction(_emoji_text(m))
            except discord.HTTPException:
                logger.warning("ReactionRoles: could not add %s to %s", _emoji_text(m), message_id)
            await asyncio.sleep(0.3)

        await self._backfill_roles(guild, message_id)

    async def _update_post_embed(self, guild: discord.Guild, message, row: dict, mappings: list[dict]):
        """Rewrite a bot post's embed (text, role list, member counts) if it changed."""
        if message.author != self.bot.user:
            return
        counts = {}
        for m in mappings:
            role = guild.get_role(int(m["role_id"]))
            if role is not None:
                counts[role.id] = len(role.members)
        embed = build_role_embed(row["title"], row["body"], mappings, counts)
        current = message.embeds[0] if message.embeds else None
        if current is not None and current.title == embed.title and current.description == embed.description:
            return
        try:
            await message.edit(content=None, embed=embed)
        except discord.HTTPException:
            logger.warning("ReactionRoles: could not edit message %s", message.id)

    async def _refresh_post(self, guild: discord.Guild, message_id: int):
        row = _get_message_row(message_id)
        if row is None or not row["managed"]:
            return
        message = await self._fetch_message(guild, int(row["channel_id"]), message_id)
        if message is not None:
            await self._update_post_embed(guild, message, row, _get_mapping_rows(message_id))

    def _mark_posts_for_roles(self, role_ids: set[int]):
        """Queue a count refresh for bot posts that list any of these roles."""
        for message_id in self._managed:
            if role_ids & set(self._role_map.get(message_id, {}).values()):
                self._dirty_posts.add(message_id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            changed = {r.id for r in set(before.roles) ^ set(after.roles)}
            self._mark_posts_for_roles(changed)

    @commands.Cog.listener()
    async def on_raw_member_remove(self, payload: discord.RawMemberRemoveEvent):
        user = payload.user
        if isinstance(user, discord.Member):
            self._mark_posts_for_roles({r.id for r in user.roles})

    async def _backfill_roles(self, guild: discord.Guild, message_id: int):
        """Give the role to anyone who already reacted (e.g. before it was mapped)."""
        emoji_roles = self._role_map.get(message_id)
        channel_id = self._channel_map.get(message_id)
        if not emoji_roles or channel_id is None:
            return
        message = await self._fetch_message(guild, channel_id, message_id)
        if message is None:
            return

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

    async def _publish_post(self, guild: discord.Guild, post_id: int) -> int | None:
        """Post a new role message requested from the admin page."""
        post = _get_post(post_id)
        if post is None or post["status"] != "pending":
            return None
        channel = guild.get_channel(int(post["channel_id"]))
        if channel is None or not hasattr(channel, "send"):
            _finish_post(post, None, "Channel not found. Check the Channel ID.")
            return None
        try:
            message = await channel.send(embed=build_role_embed(post["title"], post["body"], []))
        except discord.Forbidden:
            _finish_post(post, None, "The bot can't post in that channel (needs Send Messages and Embed Links).")
            return None
        except discord.HTTPException as e:
            _finish_post(post, None, f"Discord error: {e}")
            return None
        _finish_post(post, message.id)
        logger.info("ReactionRoles: posted role message %s in #%s", message.id, channel)
        return message.id

    async def _clear_own_reactions(self, guild: discord.Guild, channel_id: int, message_id: int):
        """Take back the bot's reactions from a message that is no longer tracked."""
        message = await self._fetch_message(guild, channel_id, message_id)
        if message is None:
            return
        for reaction in message.reactions:
            if reaction.me:
                try:
                    await message.remove_reaction(reaction.emoji, self.bot.user)
                except discord.HTTPException:
                    pass

    async def _delete_post(self, guild: discord.Guild, channel_id: int, message_id: int):
        message = await self._fetch_message(guild, channel_id, message_id)
        if message is not None and message.author == self.bot.user:
            await message.delete()

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
