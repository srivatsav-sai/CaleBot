# This example requires the 'message_content' intent.

import nextcord as discord

COMMAND_PREFIX = "c."

import nextcord
from nextcord.ext import commands

TESTING_GUILD_ID = 748394748099821648  # Replace with your guild ID

bot = commands.Bot()

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

@bot.slash_command(description="My first slash command", guild_ids=[TESTING_GUILD_ID])
async def hello(interaction: nextcord.Interaction):
    await interaction.send("Hello!")

bot.run('MTIyMTczNzIzMDI4NTE0NDA5NQ.GXVsMK.DKcf411v8ewYSxLQzRv5sSoaOWWpdPTJjnlS1I')
