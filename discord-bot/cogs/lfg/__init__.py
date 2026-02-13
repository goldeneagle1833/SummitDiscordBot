from cogs.lfg.cog import LFGCog
from cogs.lfg.match_reporting import LFGReportButtons


async def setup(bot):
    await bot.add_cog(LFGCog(bot))
