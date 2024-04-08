from imports import *

from cogModeration import HandleMod
from cogLeveling import HandleLevel
from cogLogging import HandleLog

from settings import CONFIG

TESTING_GUILD_ID = 1222575663869984778

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.presences = True
intents.message_content = True
intents.voice_states = True
intents.emojis = True
intents.moderation = True
intents.reactions = True
intents.typing = True
intents.messages = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


async def do_shutdown(client):
    await client.get_channel(CONFIG["bot_info_channel"]).send(
        CONFIG["messages"]["bot_restarting"]
    )


if __name__ == "__main__":
    # bot.remove_command("help")
    # bot.add_cog(HandleMod(bot))
    # bot.add_cog(HandleDB(bot))
    # bot.add_cog(HandleLevel(bot))
    # bot.add_cog(HandleLog(bot))

    # -- run bot --#
    try:
        bot.run(CONFIG["auth_token"])
    except KeyboardInterrupt as E:
        do_shutdown(bot)

# bot.run(os.environ['TOKEN'])
# bot.run('MTIyMTczNzIzMDI4NTE0NDA5NQ.G_0aPF.ROvNAxlCtfmt8KVhatymPP_Gf-sfj6_DlZ1hBE')
