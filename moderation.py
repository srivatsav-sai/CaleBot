import nextcord as discord
import time
import asyncio
import re
import os

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.voice_states = True  # Add this line to enable voice state intents
intents.typing = False
intents.presences = False

COMMAND_PREFIX = "c."
CLIENT = discord.Client(intents=intents)

LINK_REGEX = r"(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|www\.[a-zA-Z0-9]+\.[^\s]{2,})"
MESSAGE_COOLDOWN = 6
USER_COOLDOWN = 6
MAX_MESSAGES_PER_BURST = 3
AUDIT_LOG_CHANNEL = 1221887151650902176
ALLOWED_LINK_DOMAINS = ["youtube.com"]
ALLOWED_LINK_CHANNELS = []

message_cooldowns = {}
user_cooldowns = {}

LOG_CHANNEL_ID = 1221887151650902176  # Channel ID to post the logs

def strip_url(url):
    url = re.sub(r'^(?:https?|ftp)://', '', url)
    url = re.sub(r'/.*$', '', url)
    return url

async def log_message(message):
    if AUDIT_LOG_CHANNEL:
        audit_channel = CLIENT.get_channel(AUDIT_LOG_CHANNEL)
        if audit_channel:
            await audit_channel.send(message)

async def log_event(event_type, user, content):
    log_channel = CLIENT.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title=event_type, description=content)
        embed.set_author(name=user.name, icon_url=user.avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        await log_channel.send(embed=embed)

@CLIENT.event
async def on_ready():
    print(f'Logged in as {CLIENT.user} (ID: {CLIENT.user.id})')

@CLIENT.event
async def on_message(message):
    if message.author == CLIENT.user:
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
            return
    else:
        message_cooldowns[author] = current_time

    if author in user_cooldowns:
        if current_time - user_cooldowns[author][0] < USER_COOLDOWN:
            if len(user_cooldowns[author]) >= MAX_MESSAGES_PER_BURST:
                await message.delete()
                await message.channel.send(f"{author.mention}, you've sent too many messages in a short time. Please wait {USER_COOLDOWN - (current_time - user_cooldowns[author][0]):.2f} seconds before sending more.")
                user_cooldowns[author].pop(0)
                user_cooldowns[author].append(current_time)
            else:
                user_cooldowns[author].append(current_time)
        else:
            user_cooldowns[author] = [current_time]
    else:
        user_cooldowns[author] = [current_time]

@CLIENT.event
async def on_message_delete(message):
    await log_event("Message Deleted", message.author, message.content)

@CLIENT.event
async def on_message_edit(before, after):
    await log_event("Message Edited", before.author, f"**Before:** {before.content}\n**After:** {after.content}")

@CLIENT.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        await log_event("Voice Channel Joined", member, f"{member.mention} joined voice channel: {after.channel.name}")
    elif before.channel is not None and after.channel is None:
        await log_event("Voice Channel Left", member, f"{member.mention} left voice channel: {before.channel.name}")

CLIENT.run(os.environ['TOKEN'])
