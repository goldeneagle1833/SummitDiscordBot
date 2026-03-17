"""Custom command checks for the bot."""

from discord.ext import commands
import config


def is_bot_admin():
    """Check that allows users with administrator perms, BOT_ADMIN_ROLE_ID, or JUDGE_ROLE_ID role."""

    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        if any(role.id == config.BOT_ADMIN_ROLE_ID for role in ctx.author.roles):
            return True
        if any(role.id == config.JUDGE_ROLE_ID for role in ctx.author.roles):
            return True
        raise commands.MissingPermissions(["administrator"])

    return commands.check(predicate)
