"""Opt-in skill-based matchmaking for the Ranked queue ("Skill matching" setting).

When either player in a possible Ranked pairing has turned Skill matching on,
the pair is only made if their ratings are within an allowed gap. The gap
starts at ``START_GAP`` and widens by ``WIDEN_STEP`` every ``WIDEN_EVERY_SECONDS``
the longer-waiting of the two has been in the queue, up to ``MAX_GAP``
(Bruce's pick: 120, plus 10 every 10 seconds, up to 400). A replay of two weeks
of real queue joins (Nov 8-22, 2026) with a similar rule had most players
waiting about 20 seconds longer, the top and bottom of the ladder 1.5-2 minutes.

The rating used is the one the game would be played for: the player's season
rating on the avatar they queued with in Avatar mode, otherwise their season
rating. Players with no games yet count as the starting rating.

Matching normally happens only when someone joins, so as gaps widen two
waiting players can become a fair pair with nobody new joining. The sweep at
the bottom of this file (run from the LFG cog's 5-second loop) finds those
players and runs the normal join flow for them again.
"""

import datetime
import logging
import sqlite3

from cogs.lfg.state import lfg_queue, lfg_queue_lock, matching_web_users

logger = logging.getLogger("discord_bot")

SKILL_QUEUE = "ranked"
START_GAP = 120
WIDEN_STEP = 10
WIDEN_EVERY_SECONDS = 10
MAX_GAP = 400


def allowed_gap(waited_seconds: float) -> int:
    """Largest rating gap allowed after waiting this long."""
    steps = int(max(0.0, waited_seconds) // WIDEN_EVERY_SECONDS)
    return min(MAX_GAP, START_GAP + WIDEN_STEP * steps)


def queue_rating(user_id, avatar=None, event=None, elo_db="elo.db"):
    """The season rating this player's Ranked game would count for, or None if unreadable."""
    try:
        from services.glicko2_season import get_event, is_glicko2, load_avatar, load_player
        from services.avatar_mode import is_avatar_mode

        conn = sqlite3.connect(elo_db)
        try:
            event = event or get_event(conn)
            glicko = is_glicko2(event)
            if avatar and event and is_avatar_mode(event):
                if glicko:
                    return int(round(load_avatar(conn, event["event_id"], user_id, avatar).rating))
                from repositories.avatar_elo_repo import get_avatar_event_elo

                return int(get_avatar_event_elo(event["event_id"], user_id, avatar))
            if glicko:
                return int(round(load_player(conn, user_id).rating))
        finally:
            conn.close()
        from repositories.elo_repo import get_user_event_elo

        return int(get_user_event_elo(user_id))
    except Exception as e:
        logger.warning(f"Skill matching: could not read rating for {user_id}: {e}")
        return None


class SkillGate:
    """Decides, for one queue check, which waiting players the joiner may pair with.

    Built once per ``check_if_someone_is_lfg`` call so the opt-in list and
    ratings are each read once.
    """

    def __init__(self, joiner_id, joiner_avatar, joiner_since, candidates, now,
                 rating_fn=None, opted_fn=None):
        self.joiner_id = joiner_id
        self.joiner_avatar = joiner_avatar
        self.joiner_since = joiner_since or now
        self.now = now
        self._rating_fn = rating_fn or queue_rating
        self._ratings = {}
        try:
            if opted_fn is None:
                from repositories.skill_match_repo import skill_match_ids

                opted_fn = skill_match_ids
            self.opted = opted_fn([joiner_id, *candidates])
        except Exception as e:
            logger.warning(f"Skill matching: could not read settings, matching as usual: {e}")
            self.opted = set()

    def _rating(self, user_id, avatar):
        key = (user_id, avatar)
        if key not in self._ratings:
            self._ratings[key] = self._rating_fn(user_id, avatar)
        return self._ratings[key]

    def check(self, user_id, entry):
        """(ok, gap, allowed). ok is True when this pair may be made."""
        if self.joiner_id not in self.opted and user_id not in self.opted:
            return True, None, None
        mine = self._rating(self.joiner_id, self.joiner_avatar)
        theirs = self._rating(user_id, entry.get("avatar"))
        if mine is None or theirs is None:
            return True, None, None  # unreadable: never block a game on a read error
        waited = max(
            (self.now - self.joiner_since).total_seconds(),
            (self.now - (entry.get("queued_since") or entry["timestamp"])).total_seconds(),
        )
        gap = abs(mine - theirs)
        allowed = allowed_gap(waited)
        return gap <= allowed, gap, allowed


def build_gate(lfg_cog_queue, joiner_id, queue_type, now, joiner_avatar=None, joiner_since=None, **kw):
    """A SkillGate for a Ranked check, or None for other queues.

    When the joiner is still in the queue (a sweep re-checking a waiting
    player) their own entry gives their join time and avatar.
    """
    if queue_type != SKILL_QUEUE:
        return None
    own = lfg_cog_queue.get(joiner_id, {}).get("queues", {}).get(queue_type)
    if own:
        joiner_since = joiner_since or own.get("queued_since") or own.get("timestamp")
        joiner_avatar = joiner_avatar or own.get("avatar")
    candidates = [
        uid for uid, data in lfg_cog_queue.items()
        if uid != joiner_id and queue_type in data.get("queues", {})
    ]
    if not candidates:
        return None
    return SkillGate(joiner_id, joiner_avatar, joiner_since, candidates, now, **kw)


# --- Sweep: pair waiting players once their gap has widened enough ---------


class _Ctx:
    def __init__(self, user_id):
        self.author = type("Author", (), {"id": user_id})()


def skill_players_ready(lfg_cog, now=None):
    """(user_id, entry) for waiting Skill-matching players who now have a fair partner.

    Takes each such player out of the Ranked queue; the caller re-joins them.
    Call with ``lfg_queue_lock`` held.
    """
    from cogs.lfg.voice import (
        DEFAULT_VOICE,
        entry_voice_flexible,
        holding_for_voice,
        normalize_voice_preference,
    )
    from repositories.skill_match_repo import skill_match_ids

    now = now or datetime.datetime.now()
    waiting = {
        uid: data["queues"][SKILL_QUEUE]
        for uid, data in lfg_queue.items()
        if SKILL_QUEUE in data.get("queues", {}) and uid not in matching_web_users
    }
    if len(waiting) < 2:
        return []
    try:
        opted = skill_match_ids(list(waiting))
    except Exception as e:
        logger.warning(f"Skill matching sweep: could not read settings: {e}")
        return []
    ready = []
    taken = set()
    for uid in sorted(opted, key=lambda u: waiting[u]["timestamp"] if u in waiting else now):
        entry = waiting.get(uid)
        if not entry or uid in taken or entry.get("ladder_info"):
            continue
        if (now - entry["timestamp"]).total_seconds() >= entry["timeframe"] * 60:
            continue
        voice = normalize_voice_preference(entry.get("voice")) or DEFAULT_VOICE
        flexible = entry_voice_flexible(entry)
        partner = lfg_cog.check_if_someone_is_lfg(
            _Ctx(uid), SKILL_QUEUE, voice=voice, voice_flexible=flexible,
            voice_hold=holding_for_voice(voice, flexible, entry["timestamp"], now),
        )
        if partner is None or partner in taken:
            continue
        taken.update({uid, partner})
        user_data = lfg_queue.get(uid, {})
        user_data.get("queues", {}).pop(SKILL_QUEUE, None)
        if not user_data.get("queues"):
            lfg_queue.pop(uid, None)
        ready.append((uid, dict(entry)))
    return ready


async def release_skill_waits(bot):
    """Pair waiting Skill-matching players whose widened gap now fits someone in queue."""
    lfg_cog = bot.get_cog("LFGCog")
    if not lfg_cog:
        return
    now = datetime.datetime.now()
    async with lfg_queue_lock:
        lfg_cog.clean_expired_lfg()
        ready = skill_players_ready(lfg_cog, now)
    if not ready:
        return

    import config
    from cogs.lfg.queue import _process_queue_join
    from cogs.lfg.voice import DEFAULT_VOICE, entry_voice_flexible, holding_for_voice, normalize_voice_preference
    from cogs.lfg.voice_hold import (
        MIN_REJOIN_MINUTES,
        _DirectMessageFollowup,
        _HoldInteraction,
        _minutes_left,
    )
    from services.matchmaking_api import WebsiteInteraction

    guild = bot.get_guild(config.GUILD_ID)
    for user_id, entry in ready:
        member = guild.get_member(user_id) if guild else None
        if member is None and guild:
            try:
                member = await guild.fetch_member(user_id)
            except Exception as e:
                logger.error(f"Skill matching: could not fetch member {user_id}: {e}")
        if member is None:
            continue
        origin = entry.get("origin", "discord")
        interaction = (
            WebsiteInteraction(bot, member, guild) if origin == "sorcery_online"
            else _HoldInteraction(bot, member, guild, _DirectMessageFollowup(member))
        )
        voice = normalize_voice_preference(entry.get("voice")) or DEFAULT_VOICE
        flexible = entry_voice_flexible(entry)
        minutes = max(MIN_REJOIN_MINUTES, round(_minutes_left(entry, now)))
        logger.info(f"Skill matching: range widened for {user_id}; pairing")
        try:
            await _process_queue_join(
                bot,
                interaction,
                SKILL_QUEUE,
                minutes,
                entry.get("deck_url"),
                origin=origin,
                voice=voice,
                voice_flexible=flexible,
                voice_hold=holding_for_voice(voice, flexible, entry["timestamp"], now),
                alert_avatar=entry.get("alert_avatar", False),
                deck_avatar=entry.get("deck_avatar"),
                queued_since=entry.get("queued_since") or entry["timestamp"],
            )
        except Exception as e:
            logger.error(f"Skill matching: re-join failed for {user_id}: {e}", exc_info=True)
