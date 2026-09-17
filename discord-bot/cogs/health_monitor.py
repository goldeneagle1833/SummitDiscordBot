"""Health Monitor cog — periodically checks Summit APIs and DMs the owner on degradation."""

import asyncio
import logging
import time

import aiohttp
import discord
from discord.ext import commands, tasks

import config

logger = logging.getLogger("discord_bot")

# Thresholds
SLOW_RESPONSE_MS = 2000       # 2 seconds = slow
DOWN_TIMEOUT_S = 10            # 10 seconds = consider down
CHECK_INTERVAL_SECONDS = 300   # check every 5 minutes (outage alert within ~10 minutes)
ALERT_COOLDOWN_SECONDS = 3600  # while still failing, re-alert at most hourly

# Base URLs
WEB_APP_URL = getattr(config, "WEB_APP_URL", "https://sorcererssummit.com")
MATCHMAKING_API_HOST = "127.0.0.1"
MATCHMAKING_API_PORT = 8765
BOT_API_BASE = f"http://{MATCHMAKING_API_HOST}:{MATCHMAKING_API_PORT}"

# All endpoints to monitor, grouped by service
# (name, method, url, accept_statuses)
# accept_statuses: set of HTTP status codes considered "healthy" (beyond 2xx)
HEALTH_ENDPOINTS = [
    # --- Web App (public) ---
    # /api/health checks DBs, disk, memory, bot API, and recent 5xx rate/latency
    ("Web App - Health", "GET", f"{WEB_APP_URL}/api/health", {200}),
    ("Web App - Leaderboard Sources", "GET", f"{WEB_APP_URL}/api/leaderboard/sources", {200}),
    ("Web App - Player Lookup", "GET", f"{WEB_APP_URL}/api/player/0", {200, 404}),
    # --- Web App - PSO Relay (requires API key, expect 401/403) ---
    ("PSO Relay - Status", "GET", f"{WEB_APP_URL}/api/matchmaking/users/0/status", {401, 403}),
    # --- Bot Loopback API (direct) ---
    ("Bot API - Status", "GET", f"{BOT_API_BASE}/users/0/status", {200}),
]

# Simplified list for hourly background alerts (just core services)
ALERT_ENDPOINTS = [
    ("Web App", "GET", f"{WEB_APP_URL}/api/health", {200}),
    ("Bot Matchmaking API", "GET", f"{BOT_API_BASE}/users/0/status", {200}),
]


def _status_label(result):
    """Return a status label and whether it's healthy."""
    if result["error"]:
        return "DOWN", False
    if result.get("health_status") == "down":
        return "DOWN (checks failing)", False
    if result["status"] and result["status"] >= 500:
        return f"ERROR ({result['status']})", False
    if result["response_ms"] and result["response_ms"] > SLOW_RESPONSE_MS:
        return "SLOW", False
    if result.get("health_status") == "degraded":
        return "DEGRADED", False
    accepted = result.get("accept_statuses", set())
    if result["status"] and (200 <= result["status"] < 300 or result["status"] in accepted):
        return "OK", True
    return f"HTTP {result['status']}", False


class HealthMonitorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_alerts: dict[str, float] = {}  # service_name -> last alert timestamp
        self._consecutive_failures: dict[str, int] = {}  # track consecutive failures
        self._alerted_down: set[str] = set()  # services we've sent a failure DM for
        self.health_check_loop.start()

    def cog_unload(self):
        self.health_check_loop.cancel()

    def _should_alert(self, service: str) -> bool:
        last = self._last_alerts.get(service, 0)
        return (time.time() - last) >= ALERT_COOLDOWN_SECONDS

    def _record_alert(self, service: str):
        self._last_alerts[service] = time.time()

    async def _dm_owner(self, message: str):
        if not config.OWNER_ID:
            logger.warning("OWNER_ID not set, cannot send health alert")
            return
        try:
            owner = await self.bot.fetch_user(config.OWNER_ID)
            await owner.send(message)
        except discord.Forbidden:
            logger.warning("Cannot DM owner (DMs disabled)")
        except Exception as e:
            logger.error("Failed to DM owner health alert: %s", e)

    async def _check_endpoint(self, name: str, url: str, method: str = "GET",
                               accept_statuses: set | None = None) -> dict:
        """Check a single endpoint. Returns {name, method, url, status, response_ms, error, accept_statuses}."""
        try:
            async with aiohttp.ClientSession() as session:
                start = time.monotonic()
                req_method = getattr(session, method.lower(), session.get)
                async with req_method(url, timeout=aiohttp.ClientTimeout(total=DOWN_TIMEOUT_S)) as resp:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    result = {
                        "name": name,
                        "method": method,
                        "url": url,
                        "status": resp.status,
                        "response_ms": round(elapsed_ms),
                        "error": None,
                        "accept_statuses": accept_statuses or set(),
                    }
                    if url.endswith("/api/health"):
                        # Web app reports ok/degraded/down plus which checks fail
                        try:
                            body = await resp.json(content_type=None)
                            result["health_status"] = body.get("status")
                            result["failing"] = body.get("failing", [])
                        except (aiohttp.ContentTypeError, ValueError, AttributeError):
                            pass
                    return result
        except asyncio.TimeoutError:
            return {"name": name, "method": method, "url": url,
                    "status": None, "response_ms": None, "error": "timeout",
                    "accept_statuses": accept_statuses or set()}
        except aiohttp.ClientConnectorError:
            return {"name": name, "method": method, "url": url,
                    "status": None, "response_ms": None, "error": "connection_refused",
                    "accept_statuses": accept_statuses or set()}
        except Exception as e:
            return {"name": name, "method": method, "url": url,
                    "status": None, "response_ms": None, "error": str(e),
                    "accept_statuses": accept_statuses or set()}

    async def _run_checks(self, endpoints):
        """Run health checks against a list of endpoint tuples."""
        return await asyncio.gather(*(
            self._check_endpoint(name, url, method, accept)
            for name, method, url, accept in endpoints
        ))

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def health_check_loop(self):
        checks = await self._run_checks(ALERT_ENDPOINTS)

        for result in checks:
            service = result["name"]
            label, healthy = _status_label(result)

            if not healthy:
                self._consecutive_failures[service] = self._consecutive_failures.get(service, 0) + 1
                threshold = 3 if label == "SLOW" else 2
                if self._consecutive_failures[service] >= threshold and self._should_alert(service):
                    detail = (f"Error: `{result['error']}`" if result["error"]
                              else f"HTTP {result['status']} | {result['response_ms']}ms")
                    if result.get("failing"):
                        detail += f"\nFailing checks: {', '.join(result['failing'])}"
                    await self._dm_owner(
                        f"**{service} is {label}**\n"
                        f"{detail}\n"
                        f"Consecutive failures: {self._consecutive_failures[service]}"
                    )
                    self._record_alert(service)
                    self._alerted_down.add(service)
                logger.warning("Health check %s for %s: %s", label, service,
                               result["error"] or f"HTTP {result['status']}")
            else:
                if service in self._alerted_down:
                    # Always report recovery, even inside the re-alert cooldown
                    await self._dm_owner(
                        f"**{service} has RECOVERED**\n"
                        f"Response time: {result['response_ms']}ms | HTTP {result['status']}"
                    )
                    self._alerted_down.discard(service)
                    self._last_alerts.pop(service, None)
                    logger.info("Health check RECOVERED for %s", service)
                self._consecutive_failures[service] = 0

    async def _build_health_report(self) -> discord.Embed:
        """Run all health checks and return a detailed embed."""
        checks = await self._run_checks(HEALTH_ENDPOINTS)

        all_healthy = True
        embed = discord.Embed(title="Summit Health Report", timestamp=discord.utils.utcnow())

        for result in checks:
            label, healthy = _status_label(result)
            if not healthy:
                all_healthy = False

            if result["error"]:
                value = f"Error: `{result['error']}`"
            else:
                value = f"**{result['response_ms']}ms** | HTTP {result['status']}"
            if result.get("failing"):
                value += f"\nFailing checks: {', '.join(result['failing'])}"

            consecutive = self._consecutive_failures.get(result["name"], 0)
            if consecutive > 0:
                value += f"\nConsecutive failures: {consecutive}"

            value += f"\n`{result['method']} {result['url']}`"

            icon = {True: "\u2705", False: "\u274c"}[healthy]
            embed.add_field(
                name=f"{icon} {result['name']}: {label}",
                value=value,
                inline=False,
            )

        embed.color = discord.Color.green() if all_healthy else discord.Color.red()
        embed.set_footer(text=f"Slow threshold: {SLOW_RESPONSE_MS}ms | Check interval: {CHECK_INTERVAL_SECONDS // 60}min")
        return embed

    @commands.command(name="health")
    async def health_command(self, ctx):
        """Check the health of Summit APIs. Owner only, works in DMs."""
        if ctx.author.id != config.OWNER_ID:
            return
        embed = await self._build_health_report()
        await ctx.send(embed=embed)

    @health_check_loop.before_loop
    async def before_health_check(self):
        await self.bot.wait_until_ready()
        # Give services a moment to fully start
        await asyncio.sleep(30)


def setup(bot):
    bot.add_cog(HealthMonitorCog(bot))
