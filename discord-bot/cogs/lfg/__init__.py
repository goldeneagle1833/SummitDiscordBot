from cogs.lfg.cog import LFGCog
from cogs.lfg.match_reporting import LFGReportButtons
from cogs.lfg.persistent_confirm import PersistentMatchConfirmView


async def setup(bot):
    await bot.add_cog(LFGCog(bot))
