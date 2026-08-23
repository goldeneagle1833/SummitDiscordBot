"""Loopback-only HTTP API exposing the bot's authoritative LFG state."""

import hmac
import logging
import os
import time

from aiohttp import web
import discord

import config
from cogs.lfg.queue import LIMITED_RUN_REQUIRED_MESSAGE, _process_queue_join
from cogs.lfg.queue_definitions import enabled_queue_definitions, queue_definition, queue_is_enabled
from cogs.lfg.state import lfg_queue, lfg_queue_lock, matching_web_users, pending_web_matches
from repositories.limited_repo import get_active_arena_run
from services.card_points_service import validate_deck_points
from services.sorcery_online_matchmaking import sorcery_online_matchmaking_enabled
from services.summit_result_reporting import record_sorcery_online_result


logger = logging.getLogger("discord_bot")
VOICE_URL = "https://discord.gg/zSvyvyAVT"


class WebsiteFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, message, **_kwargs):
        self.messages.append(str(message))


class WebsiteInteraction:
    def __init__(self, bot, member, guild):
        self.user = member
        self.guild = guild
        self.channel = bot.get_channel(getattr(bot.get_cog("LFGCog"), "lfg_channel_id", 0))
        self.followup = WebsiteFollowup()


def _authorized(request):
    expected = os.getenv("DRAFT_SORCERY_API_KEY", "").strip()
    provided = request.headers.get("X-API-Key", "")
    return bool(expected and provided and hmac.compare_digest(expected, provided))


@web.middleware
async def _authentication(request, handler):
    if not _authorized(request):
        raise web.HTTPUnauthorized(text="Unauthorized")
    return await handler(request)


async def _summit_member(bot, user_id):
    if not bot.is_ready():
        raise web.HTTPServiceUnavailable(text="Summit bot is starting")
    guild = bot.get_guild(config.GUILD_ID)
    if guild is None:
        raise web.HTTPServiceUnavailable(text="Summit guild is unavailable")
    member = guild.get_member(user_id)
    if member is not None:
        return guild, member
    try:
        return guild, await guild.fetch_member(user_id)
    except discord.NotFound:
        return guild, None


def _prune_results():
    now = time.time()
    for user_id, result in list(pending_web_matches.items()):
        if result["expires_at"] <= now:
            pending_web_matches.pop(user_id, None)


async def _status(bot, user_id):
    guild, member = await _summit_member(bot, user_id)
    if not member:
        return {
            "membership": "not_member",
            "summit_invite_url": os.getenv("SUMMIT_DISCORD_INVITE", "https://discord.gg/sorcererssummit"),
            "voice_url": VOICE_URL,
            "queues": [],
            "result": None,
        }
    cog = bot.get_cog("LFGCog")
    if cog:
        cog.clean_expired_lfg()
    _prune_results()
    async with lfg_queue_lock:
        joined = lfg_queue.get(user_id, {}).get("queues", {})
        queues = []
        for definition in enabled_queue_definitions():
            waiting_count = sum(
                1 for user_data in lfg_queue.values()
                if definition["type"] in user_data.get("queues", {})
            )
            queues.append({
                "type": definition["type"],
                "label": definition["label"],
                "emoji": definition["emoji"],
                "waiting_count": waiting_count,
                "joined": definition["type"] in joined or matching_web_users.get(user_id) == definition["type"],
                "deck_mode": definition["deck_mode"],
            })
    result = pending_web_matches.get(user_id)
    if result:
        result = {key: value for key, value in result.items() if key != "expires_at"}
    return {
        "membership": "member",
        "summit_invite_url": os.getenv("SUMMIT_DISCORD_INVITE", "https://discord.gg/sorcererssummit"),
        "voice_url": VOICE_URL,
        "queues": queues,
        "result": result,
    }


async def start_matchmaking_api(bot):
    if not sorcery_online_matchmaking_enabled():
        logger.info("Sorcery Online matchmaking bot API is disabled")
        return None

    async def status(request):
        user_id = int(request.match_info["user_id"])
        return web.json_response(await _status(bot, user_id))

    async def join(request):
        user_id = int(request.match_info["user_id"])
        guild, member = await _summit_member(bot, user_id)
        if not member:
            raise web.HTTPForbidden(text="Summit membership is required")
        payload = await request.json()
        queue_type = str(payload.get("queue_type", ""))
        definition = queue_definition(queue_type)
        if not definition or not queue_is_enabled(queue_type):
            raise web.HTTPBadRequest(text="That queue is not available")
        try:
            duration = int(payload.get("duration_minutes", 30))
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="Invalid queue duration")
        if duration < 5 or duration > 240:
            raise web.HTTPBadRequest(text="Queue duration must be between 5 and 240 minutes")
        deck_url = str(payload.get("deck_url") or "").strip() or None
        run_id = None
        if definition["deck_mode"] == "required" and not deck_url:
            raise web.HTTPBadRequest(text="A deck is required for this queue")
        if queue_type == "limited":
            active_run = get_active_arena_run(user_id)
            if not (
                active_run and active_run["status"] == "active"
                and active_run["wins"] < 4 and active_run["losses"] < 2
            ):
                raise web.HTTPBadRequest(text=LIMITED_RUN_REQUIRED_MESSAGE)
            run_id = int(active_run["run_id"])
            deck_url = active_run["deck_url"]
        if queue_type == "points":
            is_valid, message, _total, _budget = await validate_deck_points(deck_url)
            if not is_valid:
                raise web.HTTPBadRequest(text=message)
        interaction = WebsiteInteraction(bot, member, guild)
        await _process_queue_join(
            bot, interaction, queue_type, duration, deck_url,
            run_id=run_id, origin="sorcery_online",
        )
        return web.json_response(await _status(bot, user_id))

    async def leave(request):
        user_id = int(request.match_info["user_id"])
        guild, member = await _summit_member(bot, user_id)
        if not member:
            raise web.HTTPForbidden(text="Summit membership is required")
        async with lfg_queue_lock:
            lfg_queue.pop(user_id, None)
            matching_web_users.pop(user_id, None)
        cog = bot.get_cog("LFGCog")
        if cog:
            await cog.update_lfg_status()
        return web.json_response(await _status(bot, user_id))

    async def acknowledge(request):
        user_id = int(request.match_info["user_id"])
        result_id = request.match_info["result_id"]
        _prune_results()
        result = pending_web_matches.get(user_id)
        if result and hmac.compare_digest(result["id"], result_id):
            pending_web_matches.pop(user_id, None)
        return web.json_response({"acknowledged": True})

    async def report_result(request):
        payload = await request.json()
        try:
            result = await record_sorcery_online_result(
                bot,
                guild_id=int(request.match_info["guild_id"]),
                pairing_id=int(request.match_info["pairing_id"]),
                queue_type=str(payload.get("queue_type", "")),
                reporter_id=int(payload["reporter_id"]),
                winner_id=int(payload["winner_id"]),
                loser_id=int(payload["loser_id"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise web.HTTPBadRequest(text=str(exc) or "Invalid result")
        except LookupError as exc:
            raise web.HTTPNotFound(text=str(exc))
        except Exception as exc:
            logger.error("Could not record Sorcery Online result: %s", exc, exc_info=True)
            raise web.HTTPInternalServerError(text="Could not record match result")
        return web.json_response(result)

    app = web.Application(middlewares=[_authentication], client_max_size=16 * 1024)
    app.router.add_get("/users/{user_id}/status", status)
    app.router.add_post("/users/{user_id}/queues", join)
    app.router.add_delete("/users/{user_id}/queues", leave)
    app.router.add_post("/users/{user_id}/results/{result_id}/ack", acknowledge)
    app.router.add_post(
        "/matches/{guild_id}/{pairing_id}/results",
        report_result,
    )
    runner = web.AppRunner(app)
    await runner.setup()
    host = os.getenv("MATCHMAKING_BOT_API_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise RuntimeError("MATCHMAKING_BOT_API_HOST must be loopback-only")
    port = int(os.getenv("MATCHMAKING_BOT_API_PORT", "8765"))
    await web.TCPSite(runner, host, port).start()
    logger.info("Summit matchmaking bot API listening on %s:%s", host, port)
    return runner
