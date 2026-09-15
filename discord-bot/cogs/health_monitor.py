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
CHECK_INTERVAL_SECONDS = 3600  # check every hour
ALERT_COOLDOWN_SECONDS = 300   # don't re-alert for same issue within 5 minutes

# Endpoints to monitor
WEB_APP_URL = config.WEB_APP_URL
MATCHMAKING_API_HOST = "127.0.0.1"
MATCHMAKING_API_PORT = 8765


class HealthMonitorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_alerts: dict[str, float] = {}  # service_name -> last alert timestamp
        self._consecutive_failures: dict[str, int] = {}  # track consecutive failures
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

    async def _check_endpoint(self, name: str, url: str) -> dict:
        """Check a single endpoint. Returns {status, response_ms, error}."""
        try:
            async with aiohttp.ClientSession() as session:
                start = time.monotonic()
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=DOWN_TIMEOUT_S)) as resp:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    return {
                        "name": name,
                        "status": resp.status,
                        "response_ms": round(elapsed_ms),
                        "error": None,
                    }
        except asyncio.TimeoutError:
            return {"name": name, "status": None, "response_ms": None, "error": "timeout"}
        except aiohttp.ClientConnectorError:
            return {"name": name, "status": None, "response_ms": None, "error": "connection_refused"}
        except Exception as e:
            return {"name": name, "status": None, "response_ms": None, "error": str(e)}

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def health_check_loop(self):
        checks = await asyncio.gather(
            self._check_endpoint(
                "Web App",
                f"{WEB_APP_URL}/api/leaderboard/online",
            ),
            self._check_endpoint(
                "Matchmaking API",
                f"http://{MATCHMAKING_API_HOST}:{MATCHMAKING_API_PORT}/users/0/status",
            ),
        )

        for result in checks:
            service = result["name"]

            if result["error"]:
                self._consecutive_failures[service] = self._consecutive_failures.get(service, 0) + 1
                # Alert after 2 consecutive failures to avoid spurious alerts
                if self._consecutive_failures[service] >= 2 and self._should_alert(service):
                    await self._dm_owner(
                        f"**{service} is DOWN**\n"
                        f"Error: `{result['error']}`\n"
                        f"Consecutive failures: {self._consecutive_failures[service]}"
                    )
                    self._record_alert(service)
                logger.warning("Health check FAILED for %s: %s", service, result["error"])

            elif result["status"] and result["status"] >= 500:
                self._consecutive_failures[service] = self._consecutive_failures.get(service, 0) + 1
                if self._consecutive_failures[service] >= 2 and self._should_alert(service):
                    await self._dm_owner(
                        f"**{service} returning errors**\n"
                        f"HTTP {result['status']} | {result['response_ms']}ms"
                    )
                    self._record_alert(service)
                logger.warning("Health check ERROR for %s: HTTP %s", service, result["status"])

            elif result["response_ms"] and result["response_ms"] > SLOW_RESPONSE_MS:
                self._consecutive_failures[service] = self._consecutive_failures.get(service, 0) + 1
                if self._consecutive_failures[service] >= 3 and self._should_alert(service):
                    await self._dm_owner(
                        f"**{service} is SLOW**\n"
                        f"Response time: {result['response_ms']}ms (threshold: {SLOW_RESPONSE_MS}ms)\n"
                        f"Consecutive slow responses: {self._consecutive_failures[service]}"
                    )
                    self._record_alert(service)
                logger.info("Health check SLOW for %s: %dms", service, result["response_ms"])

            else:
                # Healthy — reset consecutive failures and log recovery if was failing
                if self._consecutive_failures.get(service, 0) >= 2:
                    if self._should_alert(service):
                        await self._dm_owner(
                            f"**{service} has RECOVERED**\n"
                            f"Response time: {result['response_ms']}ms | HTTP {result['status']}"
                        )
                        self._record_alert(service)
                    logger.info("Health check RECOVERED for %s", service)
                self._consecutive_failures[service] = 0

    async def _build_health_report(self) -> discord.Embed:
        """Run all health checks and return an embed with the results."""
        checks = await asyncio.gather(
            self._check_endpoint(
                "Web App",
                f"{WEB_APP_URL}/api/leaderboard/online",
            ),
            self._check_endpoint(
                "Matchmaking API",
                f"http://{MATCHMAKING_API_HOST}:{MATCHMAKING_API_PORT}/users/0/status",
            ),
        )

        all_healthy = True
        embed = discord.Embed(title="Summit Health Report", timestamp=discord.utils.utcnow())

        for result in checks:
            if result["error"]:
                status_icon = "DOWN"
                value = f"Error: `{result['error']}`"
                all_healthy = False
            elif result["status"] and result["status"] >= 500:
                status_icon = "ERROR"
                value = f"HTTP {result['status']} | {result['response_ms']}ms"
                all_healthy = False
            elif result["response_ms"] and result["response_ms"] > SLOW_RESPONSE_MS:
                status_icon = "SLOW"
                value = f"{result['response_ms']}ms (threshold: {SLOW_RESPONSE_MS}ms)"
                all_healthy = False
            else:
                status_icon = "OK"
                value = f"{result['response_ms']}ms | HTTP {result['status']}"

            consecutive = self._consecutive_failures.get(result["name"], 0)
            if consecutive > 0:
                value += f"\nConsecutive failures: {consecutive}"

            embed.add_field(
                name=f"{result['name']}: {status_icon}",
                value=value,
                inline=False,
            )

        embed.color = discord.Color.green() if all_healthy else discord.Color.red()
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
