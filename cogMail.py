from imports import *

from settings import CONFIG
from settings import TESTING_GUILD_ID

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.presences = True
intents.message_content = True
intents.voice_states = True
intents.emojis = True
intents.moderation = True
# intents.channels = True
intents.reactions = True
intents.typing = True
intents.messages = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


@bot.slash_command(
    name="modmail",
    description="mail a ticket for complaint/support",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_channels=True)
async def create_text_channel(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "provide your username in server"
    ),
    text_channel: str = discord.SlashOption("modmail", "create a text channel"),
):
    await create_text_channel(create_text_channel=text_channel)
    await interaction.send(
        f"{user} has created a {text_channel} for modmail support.", ephemeral=True
    )


bot.run(CONFIG["auth_token"])
