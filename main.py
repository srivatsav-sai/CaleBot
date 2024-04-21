import nextcord as discord
import time
import re
import asyncio
import yt_dlp as youtube_dl
import os
import configparser
import tempfile
from pymongo import MongoClient
from nextcord.ext import application_checks, commands
from datetime import datetime, timedelta, timezone
from collections import deque
from pytube import Search

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

bot = commands.Bot(command_prefix="c.", intents=intents)

cluster = MongoClient("mongodb://localhost:27017/")
db = cluster["bottesting1"]
collection = db["discordserver"]
banlist = db["banlist"]

member_voice_times = {}
message_cooldowns = {}
user_cooldowns = {}
unban_tasks = asyncio.PriorityQueue()

music_queue = deque()
disconnect_now = False

ffmpeg_options = {"options": "-vn"}
ydl_opts = {
    "format": "bestaudio",
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
}

config = configparser.ConfigParser()
config.read("config.ini")

cluster = MongoClient(config.get("DATABASE", "mongodb_uri"))
db = cluster[config.get("DATABASE", "database_name")]
collection = db[config.get("DATABASE", "collection_name")]
banlist = db[config.get("DATABASE", "banlist_collection")]

TARGETING_VOICE_CHANNELS = [
    int(x) for x in config.get("VOICE", "targeting_voice_channels").split(",")
]
LINK_REGEX = config.get("ANTI_LINK", "link_regex")
MESSAGE_COOLDOWN = config.getint("ANTI_SPAM", "message_cooldown")
USER_COOLDOWN = config.getint("ANTI_SPAM", "user_cooldown")
MAX_MESSAGES_PER_BURST = config.getint("ANTI_SPAM", "max_messages_per_burst")
AUDIT_LOG_CHANNEL = config.getint("CHANNELS", "bot_audit_channel")
ALLOWED_LINK_DOMAINS = config.get("ANTI_LINK", "allowed_link_domains").split(",")
ALLOWED_LINK_CHANNELS = [
    int(x) for x in config.get("ANTI_LINK", "allowed_link_channels").split(",")
]

# Logging functions


async def log_message(message):
    if AUDIT_LOG_CHANNEL:
        audit_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
        if audit_channel:
            await audit_channel.send(message)


async def log_event(event_type, user, content):
    if AUDIT_LOG_CHANNEL:
        log_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
        if log_channel:
            embed = discord.Embed(title=event_type, description=content)
            embed.set_author(
                name=user.name, icon_url=user.avatar.url if user.avatar else ""
            )
            embed.set_footer(text=f"User ID: {user.id}")
            await log_channel.send(embed=embed)


# Anti-link functions


def strip_url(url):
    url = re.sub(r"^(?:https?|ftp)://", "", url)
    url = re.sub(r"/.*$", "", url)
    return url


# Bot events


@bot.event
async def on_ready():
    print(f"{bot.user} has logged in")
    # guild_obj = bot.get_guild(TESTING_GUILD_ID)
    # bans = await guild_obj.bans().flatten()
    # print(bans)
    # for ban in bans:
    #     post = {"_id": bans.user.id, "name": bans.user.name}
    #     banlist.insert_one(post)


async def check_level_up(channel, message, collection):
    query = {"_id": message.author.id}
    user = collection.find_one(query)

    if not user:
        post = {"_id": message.author.id, "score": 0, "currency": 0, "level": 0}
        collection.insert_one(post)
        return

    score = user.get("score", 0)
    if score % 100 == 0:
        level = user.get("level", 0)
        log_message = f"{message.author.mention}"
        await channel.send(
            f"Congratulations, {log_message}! You have reached level {level}!"
        )
    if score % 10 == 0:
        currency = user.get("currency", 0)
        log_message = f"{message.author.mention}"
        await channel.send(
            f"Congratulations, {log_message}! You now have {currency} unit{'s' if  currency > 1 else ''} currency!"
        )


async def schedule_unban_task(
    user_to_unban: discord.Member, guild: discord.Guild, unban_time: datetime
):

    delta = unban_time - datetime.now(datetime.timezone.utc)
    delay = max(delta.total_seconds(), 0)
    task = (delay, user_to_unban, guild)

    await unban_tasks.put(task)
    print(f"User {user_to_unban} scheduled for unban at {unban_time}")


async def background_unban_task():
    while True:
        delay, user_to_unban, guild = await unban_tasks.get()

        if delay <= 0:
            await user_to_unban.unban()
            print(f"Unbanned user {user_to_unban} (scheduled task)")
        else:
            await unban_tasks.put((delay, user_to_unban, guild))

        await asyncio.sleep(5)


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    print(message.author, message.channel.name, message.content, message.embeds)

    if message.author.id != bot.application_id:
        await log_event("Message sent", message.author, message.content)

    # anti-link system

    if message.channel.id not in ALLOWED_LINK_CHANNELS:
        matches = re.findall(LINK_REGEX, message.content, re.IGNORECASE)
        for match in matches:
            if strip_url(match) not in ALLOWED_LINK_DOMAINS:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, links are not allowed in this channel."
                )

    author = message.author
    current_time = time.time()

    # anti-spam & anti-nuke systems
    if author in message_cooldowns:
        if current_time - message_cooldowns[author] < MESSAGE_COOLDOWN:
            if message:
                await message.delete()
                await message.channel.send(
                    f"{author.mention}, please wait {MESSAGE_COOLDOWN - (current_time - message_cooldowns[author]):.2f} seconds before sending another message."
                )
                delta = timedelta(minutes=1)
                await author.timeout(
                    timeout=delta,
                    reason=f"{author.mention}, please wait {MESSAGE_COOLDOWN - (current_time - message_cooldowns[author]):.2f} seconds before sending another message.",
                )
            return
    else:
        message_cooldowns[author] = current_time

    if author in user_cooldowns:
        if current_time - user_cooldowns[author][0] < USER_COOLDOWN:
            if len(user_cooldowns[author]) >= MAX_MESSAGES_PER_BURST:
                await message.delete()
                await message.channel.send(
                    f"{author.mention}, you've sent too many messages in a short time. Please wait {USER_COOLDOWN - (current_time - user_cooldowns[author][0]):.2f} seconds before sending more."
                )
                delta = timedelta(minutes=1)
                await author.timeout(
                    timeout=delta,
                    reason=f"{author.mention}, you've sent too many messages in a short time. Please wait {USER_COOLDOWN - (current_time - user_cooldowns[author][0]):.2f} seconds before sending more.",
                )
                user_cooldowns[author].pop(0)
                user_cooldowns[author].append(current_time)
            else:
                user_cooldowns[author].append(current_time)
        else:
            user_cooldowns[author] = [current_time]
    else:
        user_cooldowns[author] = [current_time]

    # Level and Currency System

    myquery = {"_id": message.author.id}
    if collection.count_documents(myquery) == 0:
        if "" in str(message.content.lower()):
            post = {
                "_id": message.author.id,
                "score": 1,
                "currency": 1,
                "level": 1,
            }
            collection.insert_one(post)
    else:
        if "" in str(message.content.lower()):
            query = {"_id": message.author.id}
            user = collection.find(query)
            for result in user:
                old_score = result["score"]
                old_currency = result["currency"]
            score = old_score + 1
            level = score // 100
            currency = old_currency + 1
            collection.update_one(
                query,
                {
                    "$set": {
                        "score": score,
                        "currency": currency,
                        "level": level,
                    }
                },
            )
    await check_level_up(message.channel, message, collection)
    await bot.process_commands(message)


@bot.event
async def on_message_delete(message):
    if message.author.id != bot.application_id:
        await log_event("Message Deleted", message.author, message.content)


@bot.event
async def on_message_edit(before, after):
    if before.author.id != bot.application_id and after.author.id != bot.application_id:
        await log_event(
            "Message Edited",
            before.author,
            f"**Before:** {before.content}\n**After:** {after.content}",
        )


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id != bot.application_id:
        target_voice_channel_ids = TARGETING_VOICE_CHANNELS

        if (
            before.channel is None
            and after.channel is not None
            and after.channel.id in target_voice_channel_ids
        ) or (
            before.channel is not None
            and before.channel.id in target_voice_channel_ids
            and after.channel is None
        ):
            channel_id = after.channel.id if after.channel else before.channel.id
            channel_name = after.channel.name if after.channel else before.channel.name

            if before.channel is None:
                member_voice_times[(member, channel_id)] = datetime.now(timezone.utc)
                await log_event(
                    "Voice Channel Joined",
                    member,
                    f"{member.mention} joined voice channel: {channel_name}",
                )
            else:
                join_time = member_voice_times.get((member, channel_id))
                if join_time:
                    delta = datetime.now(timezone.utc) - join_time
                    del member_voice_times[(member, channel_id)]
                    log_message = f"{member.name} (ID: {member.id}) stayed in {channel_name} for {delta.seconds} seconds."
                    await log_event(
                        "Voice Channel Left (Duration)", member, log_message
                    )


@bot.event
async def on_member_update(before, after):
    if before.author.id != bot.application_id and after.author.id != bot.application_id:
        if before.roles != after.roles:
            added_roles = [role for role in after.roles if role not in before.roles]
            removed_roles = [role for role in before.roles if role not in after.roles]
            log_message = f"Member Role Update: {after.name} (ID: {after.id})\n"
            if added_roles:
                log_message += (
                    f"Added Roles: {', '.join(role.name for role in added_roles)}\n"
                )
            if removed_roles:
                log_message += (
                    f"Removed Roles: {', '.join(role.name for role in removed_roles)}\n"
                )
            await log_event("Member Updated", before, f"{log_message}")


@bot.event
async def on_reaction_add(reaction, user):
    if user.id != bot.application_id:
        message = reaction.message
        emoji = reaction.emoji

        log_message = f"By User: {user.name}\n"
        log_message += f"Message Author: {message.author.name}\n"
        log_message += f"Message Channel: {message.channel.name}\n"
        log_message += f"Message: {message.content}\n"
        log_message += f"Reaction: {emoji}"
        await log_event("Reaction Added", user, f"{log_message}")


# Slash commands


@bot.slash_command(
    name="get_currency",
    description="To show how much currency you have",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
async def getCurrency(interaction: discord.Interaction):
    query = {"_id": interaction.user.id}
    user = collection.find_one(query)
    currency = user.get("currency", 0) if user else 0

    await interaction.send(f"You have {currency} currency", ephemeral=True)


@bot.slash_command(
    name="get_level",
    description="To show how many levels you gained",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
async def getLevels(interaction: discord.Interaction):
    query = {"_id": interaction.user.id}
    user = collection.find_one(query)
    level = user.get("level", 0) if user else 0

    await interaction.send(f"You have reached level {level}", ephemeral=True)


@bot.slash_command(
    name="kick",
    description="Kick a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberKick(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption("kick", "Kick a user from server"),
    reason: str = discord.SlashOption(
        "reason", "Provide a reason to kick the selected user"
    ),
):
    await interaction.guild.kick(user, reason=reason)
    await interaction.send(f"{user} has been kicked", ephemeral=True)


@bot.slash_command(
    name="ban",
    description="Ban a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberBan(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption("ban", "Ban a user from server"),
    delete_message_days: int = discord.SlashOption(
        "delete_message_days", "Delete this user's previous messages up to"
    ),
    reason: str = discord.SlashOption(
        "reason", "Provide a reason to ban the selected user"
    ),
):
    await interaction.guild.ban(
        user, delete_message_days=delete_message_days, reason=reason
    )
    await interaction.send(f"{user} has been banned", ephemeral=True)


@bot.slash_command(
    name="temp_ban",
    description="temporarily ban a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberTempBan(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption("ban", "ban a user from server"),
    duration: int = discord.SlashOption(
        name="duration",
        description="Ban duration in days (default: 10 days)",
        required=False,
    ),
    delete_message_days: int = discord.SlashOption(
        "delete_message_days", "delete this user's previous messages upto"
    ),
    reason: str = discord.SlashOption(
        "reason", "provide a reason to ban the selected user"
    ),
):
    author = interaction.user
    guild = interaction.guild
    if not duration:
        duration = 10

    unban_time = datetime.now(datetime.timezone.utc) + timedelta(days=duration)

    reason_with_time = (
        f"Temporarily banned (unban at {unban_time.strftime('%H:%M:%S %Z')})"
    )
    if reason:
        reason_with_time += f": {reason}"
    await user.ban(reason=reason_with_time)

    await schedule_unban_task(user, guild, unban_time)

    await interaction.response.send_message(
        f"Temporarily banned {user.name}#{user.discriminator} for {duration} day(s)."
    )

    await guild.ban(
        user, duration, delete_message_days=delete_message_days, reason=reason
    )
    await interaction.send(f"{user} has been banned", ephemeral=True)


@bot.slash_command(
    name="unban",
    description="Unban a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberUnban(
    interaction: discord.Interaction,
    user: str = discord.SlashOption("unban", "Unban a user from server"),
    reason: str = discord.SlashOption(
        "reason", "Provide a reason to unban the selected user"
    ),
):
    await interaction.guild.unban(discord.Object(id=user), reason=reason)
    await interaction.send(f"{user} has been unbanned", ephemeral=True)


@bot.slash_command(
    name="timeout",
    description="Timeout a person in server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_messages=True)
async def memberMute(
    interaction: discord.Interaction,
    timeout: int = discord.SlashOption(
        "timeout", "Provide an amount of time to mute in minutes"
    ),
    user: discord.Member = discord.SlashOption(
        "user", "Timeout a user in minutes in server"
    ),
    reason: str = discord.SlashOption(
        "reason", "Provide a reason to timeout the selected user"
    ),
):
    delta = timedelta(minutes=timeout)
    await user.timeout(timeout=delta, reason=reason)
    await interaction.send(f"{user} has been muted", ephemeral=True)


@bot.slash_command(
    name="nickname",
    description="Nickname a person in server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(manage_nicknames=True)
async def changeNick(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "Select a user to change nickname in server"
    ),
    nickname: str = discord.SlashOption(
        "nickname", "Enter a new nickname for the selected user"
    ),
):
    await user.edit(nick=nickname)
    await interaction.send(f"Nickname of {user} has been changed.", ephemeral=True)


@bot.slash_command(
    name="roles",
    description="Manage roles of a person in server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_guild_permissions(manage_roles=True)
async def manageRoles(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "Select a user to manage their roles in server"
    ),
    manage_roles: discord.Role = discord.SlashOption(
        "roles", "Manage roles for the selected user"
    ),
):
    await user.edit(roles=[manage_roles])
    await interaction.send(f"Roles have been updated for {user}", ephemeral=True)


@bot.slash_command(
    name="drag",
    description="Drag a person to a voice channel in server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(move_members=True)
async def voiceDrag(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "Select a user to drag to a voice channel"
    ),
    change_vc: discord.VoiceChannel = discord.SlashOption(
        "drag", "Change VC for the selected user"
    ),
):
    await user.move_to(change_vc)
    await interaction.send(f"{user} has been dragged to {change_vc}", ephemeral=True)


@bot.slash_command(
    name="create_text",
    description="Create a text channel in the server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
async def createText(
    interaction: discord.Interaction,
    create_text: str = discord.SlashOption("name", "Give a name for the Text Channel"),
):
    query = {"_id": interaction.user.id}
    user = collection.find_one(query)
    currency = user.get("currency", 0) if user else 0
    guild = interaction.guild
    if currency >= 10:
        collection.update_one(query, {"$set": {"currency": currency - 10}})

        text_channel = await guild.create_text_channel(create_text)

        await interaction.response.send_message(
            f"{text_channel.name} text channel has been created.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "You do not have enough currency to create a text channel.", ephemeral=True
        )


@bot.slash_command(
    name="help",
    description="Shows a list of all slash commands in the server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_guild_permissions(administrator=True)
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="My Commands")

    ban_desc = "To ban a user from the server."
    unban_desc = "To unban a user from the server."
    kick_desc = "To kick a user from the server."
    timeout_desc = "To timeout/mute a user in the server."
    nick_desc = "To change nickname of a user in the server."
    roles_desc = "To change roles of a user in the server."
    drag_desc = "To drag a user between VCs in the server."
    currency_desc = "To show how much currency you have."
    level_desc = "To show how many levels you have gained."
    text_desc = "To create a text channel using 10 currency."
    play_desc = "To play/add songs into the music bot."
    pause_desc = "To pause music using the music bot."
    resume_desc = "To resume music using the music bot."
    skip_desc = "To skip music using the music bot."
    disconnect_desc = "To disconnect the music bot."

    embed.add_field(name="`/ban`", value=ban_desc, inline=False)
    embed.add_field(name="`/unban`", value=unban_desc, inline=False)
    embed.add_field(name="`/kick`", value=kick_desc, inline=False)
    embed.add_field(name="`/timeout`", value=timeout_desc, inline=False)
    embed.add_field(name="`/nickname`", value=nick_desc, inline=False)
    embed.add_field(name="`/roles`", value=roles_desc, inline=False)
    embed.add_field(name="`/drag`", value=drag_desc, inline=False)
    embed.add_field(name="`/get_currency`", value=currency_desc, inline=False)
    embed.add_field(name="`/get_level`", value=level_desc, inline=False)
    embed.add_field(name="`/create_text`", value=text_desc, inline=False)
    embed.add_field(
        name="`c.play or c.p or c.add or c.next or c.connect or c.join`",
        value=play_desc,
        inline=False,
    )
    embed.add_field(name="`c.pause`", value=pause_desc, inline=False)
    embed.add_field(name="`c.resume or c.r`", value=resume_desc, inline=False)
    embed.add_field(name="`c.skip`", value=skip_desc, inline=False)
    embed.add_field(
        name="`c.disconnect or c.dc or c.boot or c.stop`",
        value=disconnect_desc,
        inline=False,
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# Music functions


def delete_songs(temp_dir):
    for file in os.listdir(temp_dir):
        if file.endswith(".mp3"):
            os.remove(os.path.join(temp_dir, file))


def get_youtube_url(search_term, result_index=0):
    results = Search(search_term).results
    if results:
        return results[result_index].watch_url
    else:
        return None


async def play_queue(ctx, temp_dir):
    global music_queue
    global disconnect_now
    while music_queue:
        url = music_queue.popleft()

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            files = os.listdir(temp_dir)
            audio_file = next(file for file in files if file.endswith(".mp3"))
            file_path = os.path.join(temp_dir, audio_file)
            source = discord.FFmpegPCMAudio(file_path, **ffmpeg_options)

            ctx.voice_client.play(source)
            while ctx.guild.voice_client.is_connected():
                if disconnect_now:
                    disconnect_now = False
                    break
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Error playing song: {e}")
            await ctx.send(f"An error occurred while playing {url}. Skipping...")

    if not music_queue:
        await ctx.voice_client.disconnect()
        music_queue = deque()


# Music bot commands


@bot.command(name="play", aliases=["connect", "join", "next", "add", "p"])
async def streamx(ctx, url):
    global music_queue
    if "youtu" not in url:
        url = get_youtube_url(url)

    music_queue.append(url)
    await ctx.send("Song added to the queue.")

    if not ctx.message.author.voice:
        await ctx.send("You need to be in a voice channel to play music.")
        return
    voiceChannel = ctx.message.author.voice.channel

    if ctx.guild.voice_client and ctx.guild.voice_client.is_connected():
        pass
    else:
        await voiceChannel.connect()
        await ctx.send(f"Playing on channel {ctx.message.author.voice.channel}")

        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts["outtmpl"] = os.path.join(temp_dir, "%(id)s.%(ext)s")
            await play_queue(ctx, temp_dir)


@bot.command(name="resume", aliases=["r"])
async def resume(ctx):
    if ctx.guild.voice_client and ctx.guild.voice_client.is_connected():
        ctx.voice_client.resume()
        await ctx.send("Playback resumed.")
    else:
        await ctx.send(
            "Not connected to a voice channel or no song was previously playing."
        )


@bot.command(name="pause")
async def pause(ctx):
    ctx.voice_client.pause()
    await ctx.send("Playback paused.")


@bot.command(name="disconnect", aliases=["dc", "boot", "stop"])
async def disconnect(ctx):
    global music_queue
    global disconnect_now

    music_queue = deque()

    disconnect_now = True
    await asyncio.sleep(2)

    with tempfile.TemporaryDirectory() as temp_dir:
        delete_songs(temp_dir)

    await ctx.send("Player disconnected.")


@bot.command(name="skip")
async def skip(ctx):
    global disconnect_now

    ctx.voice_client.stop()

    disconnect_now = True
    await asyncio.sleep(2)

    ctx.voice_client.resume()

    await ctx.send("Song skipped.")


bot.run(config.get("BOT", "auth_token"))
