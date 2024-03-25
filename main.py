# This example requires the 'message_content' intent.

import nextcord as discord
from datetime import datetime,timedelta
import os

COMMAND_PREFIX = "c."
from nextcord.ext import commands

TESTING_GUILD_ID = 748394748099821648  # Replace with your guild ID

bot = commands.Bot()

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

@bot.slash_command(description="My first slash command", guild_ids=[TESTING_GUILD_ID])
async def hello(interaction: discord.Interaction):
    await interaction.send("Hello!")

# @bot.slash_command(description="Ban List", guild_ids=[TESTING_GUILD_ID])
# async def banlist(interaction: discord.Interaction):
#     async for ban in interaction.guild.bans():
#         await interaction.send(f"{ban.user}")

@bot.slash_command(name="kick", description="kick a person from server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
async def memberKick(interaction: discord.Interaction, user: discord.User=discord.SlashOption("kick", "kick a user from server"), reason: str=discord.SlashOption("reason", "provide a reason to kick the selected user")):
    await interaction.guild.kick(user, reason=reason)
    await interaction.send(f"test kick{user}", ephemeral=True)

@bot.slash_command(name="ban", description="ban a person from server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
async def memberBan(interaction: discord.Interaction, user: discord.User=discord.SlashOption("ban", "ban a user from server"), reason: str=discord.SlashOption("reason", "provide a reason to ban the selected user")):
    await interaction.guild.ban(user, reason=reason)
    await interaction.send(f"test ban{user}", ephemeral=True)

@bot.slash_command(name="unban", description="unban a person from server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
async def memberUnban(interaction: discord.Interaction, user: str=discord.SlashOption("unban", "unban a user from server"), reason: str=discord.SlashOption("reason", "provide a reason to unban the selected user")):
    await interaction.guild.unban(discord.User(id=user), reason=reason)
    await interaction.send(f"test unban{user}", ephemeral=True)

@bot.slash_command(name="timeout", description="timeout a person in server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
async def memberMute(interaction: discord.Interaction, timeout:int , user: discord.Member=discord.SlashOption("user", "timeout a user in minutes in server"), reason: str=discord.SlashOption("reason", "provide a reason to timeout the selected user")):
    delta=timedelta(minutes=timeout)
    await user.timeout(timeout=delta , reason=reason)
    await interaction.send(f"test mute{user}", ephemeral=True)

bot.run(os.environ['TOKEN'])
