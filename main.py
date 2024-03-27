import nextcord as discord
from nextcord.ext import application_checks
from nextcord.ext import commands
from datetime import datetime,timedelta
import os
import time
import asyncio
import re

# COMMAND_PREFIX = "c."
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.presences = False
intents.message_content = True
intents.voice_states = True
intents.emojis = True
intents.moderation = True
intents.reactions = True
intents.typing = True
intents.messages = True


TESTING_GUILD_ID = 748394748099821648
bot = discord.Client(intents=intents)
# bot = commands.Bot()

LINK_REGEX = r"(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|www\.[a-zA-Z0-9]+\.[^\s]{2,})"
MESSAGE_COOLDOWN = 60
USER_COOLDOWN = 60
MAX_MESSAGES_PER_BURST = 5
AUDIT_LOG_CHANNEL = 1222575735332409495
ALLOWED_LINK_DOMAINS = ["youtube.com"]
ALLOWED_LINK_CHANNELS = []

message_cooldowns = {}
user_cooldowns = {}

def strip_url(url):
    url = re.sub(r'^(?:https?|ftp)://', '', url)
    url = re.sub(r'/.*$', '', url)
    return url

async def log_message(message):
    if AUDIT_LOG_CHANNEL:
        audit_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
        if audit_channel:
            await audit_channel.send(message)

async def log_event(event_type, user, content):
    log_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
    if log_channel:
        embed = discord.Embed(title=event_type, description=content)
        embed.set_author(name=user.name, icon_url=user.avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        await log_channel.send(embed=embed)

@bot.event
async def on_message_delete(message):
    await log_event("Message Deleted", message.author, message.content)

@bot.event
async def on_message_edit(before, after):
    await log_event("Message Edited", before.author, f"**Before:** {before.content}\n**After:** {after.content}")

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        await log_event("Voice Channel Joined", member, f"{member.mention} joined voice channel: {after.channel.name}")
    elif before.channel is not None and after.channel is None:
        await log_event("Voice Channel Left", member, f"{member.mention} left voice channel: {before.channel.name}")

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        added_roles = [role for role in after.roles if role not in before.roles]
        removed_roles = [role for role in before.roles if role not in after.roles]
        log_message = f"Member Role Update: {after.name} (ID: {after.id})\n"
        if added_roles:
            log_message += f"Added Roles: {', '.join(role.name for role in added_roles)}\n"
        if removed_roles:
            log_message += f"Removed Roles: {', '.join(role.name for role in removed_roles)}\n"
        await log_event("Member Updated", before, f"{log_message}")

@bot.event
async def on_reaction_add(reaction, user):
    message = reaction.message
    emoji = reaction.emoji

    log_message = f"By User: {user.name}\n"
    log_message += f"Message Author: {message.author.name}\n"
    log_message += f"Message Channel: {message.channel.name}\n"
    log_message += f"Message: {message.content}\n"
    log_message += f"Reaction: {emoji}"
    await log_event("Reaction Added", user , f"{log_message}")

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    print(message.author, message.channel.name, message.content, message.embeds)

    matches = re.findall(LINK_REGEX, message.content, re.IGNORECASE)
    for match in matches:
        if strip_url(match) not in ALLOWED_LINK_DOMAINS:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, links are not allowed in this channel.")

    author = message.author
    current_time = time.time()

    if author in message_cooldowns:
        if current_time - message_cooldowns[author] < MESSAGE_COOLDOWN:
            if message:
                await message.delete()
                await message.channel.send(f"{author.mention}, please wait {MESSAGE_COOLDOWN - (current_time - message_cooldowns[author]):.2f} seconds before sending another message.")
                delta=timedelta(minutes=1)
                await author.timeout(timeout=delta , reason= f"{author.mention}, please wait {MESSAGE_COOLDOWN - (current_time - message_cooldowns[author]):.2f}seconds before sending another message.")
            return
    else:
        message_cooldowns[author] = current_time

    if author in user_cooldowns:
        if current_time - user_cooldowns[author][0] < USER_COOLDOWN:
            if len(user_cooldowns[author]) >= MAX_MESSAGES_PER_BURST:
                await message.delete()
                await message.channel.send(f"{author.mention}, you've sent too many messages in a short time. Please wait {USER_COOLDOWN - (current_time - user_cooldowns[author][0]):.2f} seconds before sending more.")
                delta=timedelta(minutes=1)
                await author.timeout(timeout=delta , reason= f"{author.mention}, you've sent too many messages in a short time. Please wait {USER_COOLDOWN - (current_time - user_cooldowns[author][0]):.2f} seconds before sending more.")
                user_cooldowns[author].pop(0)
                user_cooldowns[author].append(current_time)
            else:
                user_cooldowns[author].append(current_time)
        else:
            user_cooldowns[author] = [current_time]
    else:
        user_cooldowns[author] = [current_time]


@bot.slash_command(description="My first slash command", guild_ids=[TESTING_GUILD_ID])
async def hello(interaction: discord.Interaction):
    await interaction.send("Hello!")

@bot.slash_command(name="kick", description="kick a person from server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberKick(interaction: discord.Interaction, user: discord.User=discord.SlashOption("kick", "kick a user from server"), reason: str=discord.SlashOption("reason", "provide a reason to kick the selected user")):
    await interaction.guild.kick(user, reason=reason)
    await interaction.send(f"test kick{user}", ephemeral=True)

@bot.slash_command(name="ban", description="ban a person from server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberBan(interaction: discord.Interaction, user: discord.User=discord.SlashOption("ban", "ban a user from server") , reason: str=discord.SlashOption("reason", "provide a reason to ban the selected user")):
    await interaction.guild.ban(user, reason=reason)
    await interaction.send(f"test ban{user}", ephemeral=True)

@bot.slash_command(name="unban", description="unban a person from server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberUnban(interaction: discord.Interaction, user: str=discord.SlashOption("unban", "unban a user from server"), reason: str=discord.SlashOption("reason", "provide a reason to unban the selected user")):
    await interaction.guild.unban(discord.User(id=user), reason=reason)
    await interaction.send(f"test unban{user}", ephemeral=True)

@bot.slash_command(name="timeout", description="timeout a person in server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberMute(interaction: discord.Interaction, timeout:int , user: discord.Member=discord.SlashOption("user", "timeout a user in minutes in server"), reason: str=discord.SlashOption("reason", "provide a reason to timeout the selected user")):
    delta=timedelta(minutes=timeout)
    await user.timeout(timeout=delta , reason=reason)
    await interaction.send(f"test mute{user}", ephemeral=True)

@bot.slash_command(name="nickname", description="nickname a person in server", guild_ids=[TESTING_GUILD_ID])
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_nicknames=True)
async def changeNick(interaction: discord.Interaction , user: discord.Member=discord.SlashOption("user", "select a user to change nickname in server"), nickname: str=discord.SlashOption("nickname", "enter a new nickname for the selected user")):
    await user.edit(nick=nickname)
    await interaction.send(f"test nickname{user}", ephemeral=True)

# bot.run(os.environ['TOKEN'])
bot.run('MTIyMTczNzIzMDI4NTE0NDA5NQ.G_0aPF.ROvNAxlCtfmt8KVhatymPP_Gf-sfj6_DlZ1hBE')