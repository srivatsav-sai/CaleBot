import nextcord as discord
import time
import re
import asyncio
import youtube_dl as yt_dlp
import os
import configparser
import tempfile
import aiohttp
import motor
import json
import requests
from youtube_dl import YoutubeDL
from pymongo import MongoClient, ReturnDocument
from nextcord import FFmpegOpusAudio
from nextcord.ext import application_checks, commands
from datetime import datetime, timedelta, timezone
from collections import deque
from pytube import Search
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.operations import UpdateOne


intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.presences = True
intents.message_content = True
intents.voice_states = True
intents.emojis = True
intents.moderation = True
intents.dm_messages = True
intents.reactions = True
intents.typing = True
intents.messages = True

bot = commands.Bot(command_prefix="c.", intents=intents)

member_voice_times = {}
message_cooldowns = {}
user_cooldowns = {}
user_messages = {}
phone_number_regex = r"\d{10,}"
unban_tasks = asyncio.PriorityQueue()

music_queue = {}
colors = {
    "error": 0xF54257,
    "success": 0x6CF257,
    "neutral": 0x43CCC3,
    "spotify": 0x1DB954,
    "youtube": 0xC4302B,
    "fallback": 0xC7979,
    "apple": 0xFC3C44,
    "other": 0xEBA434,
}

disconnect_now = False
is_looping = False

yt_dlp.utils.bug_reports_message = lambda: ""
ffmpegOpts = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_on_network_error 1",
    "options": "-vn",
}
ytdlOpts = {
    "format": "bestaudio",
    "noplaylist": True,
    "default_search": "auto",
}

config = configparser.ConfigParser()
config.read("config.ini")

cluster = MongoClient(config.get("DATABASE", "mongodb_uri"))
db = cluster[config.get("DATABASE", "database_name")]
currency_collection = db[config.get("DATABASE", "currency_collection")]
ban_collection = db[config.get("DATABASE", "ban_collection")]
kick_collection = db[config.get("DATABASE", "kick_collection")]
warn_collection = db[config.get("DATABASE", "warn_collection")]
drag_request_collection = db[config.get("DATABASE", "dragrequest_collection")]

drag_request_model = {
    "_id": ObjectId(),
    "requester_id": int,
    "requested_user_id": int,
    "requested_channel_id": int,
    "timestamp": datetime.now(),
}

TESTING_GUILD_ID = config.get("GUILD", "testing_guild_id")
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
ADMIN_ROLE = config.getint("GUILD", "admin_role_id")
MOD_ROLE = config.getint("GUILD", "mod_role_id")
MOD_CHANNEL_ID = config.getint("CHANNELS", "mod_channel")
MOD_MAIL_ROLE_ID = config.getint("GUILD", "mod_mail_role_id")
AUTO_ASSIGN_ROLE_ID = config.getint("GUILD", "auto_role_id")


# Music functions


def setup():
    voices = bot.voice_clients
    music_queue.clear()
    if voices is not None:
        for voice in voices:
            bot.loop.create_task(voice.disconnect())


def now_playing(ctx):
    guild_id = TESTING_GUILD_ID
    if guild_id not in music_queue.keys():
        music_queue[guild_id] = []
    voice = ctx.channel.guild.voice_client
    if voice is None:
        return None
    if voice.is_playing():
        return music_queue[guild_id][0]


def get_current_song(ctx):
    guild_id = TESTING_GUILD_ID
    if guild_id not in music_queue.keys():
        music_queue[guild_id] = []
    voice = ctx.channel.guild.voice_client
    if voice is None:
        return None
    return music_queue[guild_id][0]


def next(ctx):
    guild_id = TESTING_GUILD_ID
    if len(music_queue[guild_id]) > 1:
        music_queue[guild_id].pop(0)
        return music_queue[guild_id][0]
    else:
        music_queue[guild_id] = []
        return None


def addsong(ctx, arg):
    if TESTING_GUILD_ID not in music_queue.keys():
        music_queue[TESTING_GUILD_ID] = []
    lst = args_to_url(arg)
    if lst != ():
        url, src, thumb, title = lst
        music_queue[TESTING_GUILD_ID].append([url, src, thumb, title, ctx])
        return url, src, thumb, title, ctx
    else:
        embed = discord.Embed(title="Song wasn't found.", color=colors["neutral"])
        ctx.send(embed=embed)
        raise Exception("Song wasn't found.")


def clear(ctx):
    guild_id = TESTING_GUILD_ID
    music_queue[guild_id] = []
    return None


def remove(id):
    if TESTING_GUILD_ID not in music_queue.keys():
        music_queue[TESTING_GUILD_ID] = []
    music_queue[TESTING_GUILD_ID].pop(id)
    return None


def args_to_url(args):
    if type(args) is tuple:
        args = " ".join(args)
    with YoutubeDL(ytdlOpts) as ytdl:
        if args.find("https://") != -1 or args.find("http://") != -1:
            if (
                args.find("https://www.youtube.com") != -1
                or args.find("https://youtu.be") != -1
            ):
                src = "youtube"
                ytdl_data = ytdl.extract_info(args, download=False)
                title = ytdl_data["title"]
                url = ytdl_data["formats"][1]["url"]
                thumb = ytdl_data["thumbnail"]
                return url, src, thumb, title
            else:
                args = args.replace(" ", "")
                if args.find("spotify") != -1:
                    src = "spotify"
                elif args.find("apple") != -1:
                    src = "apple"
                else:
                    src = "other"
                apiurl = "https://api.song.link/v1-alpha.1/links?url=" + args
                try:
                    response = json.loads(requests.get(apiurl).text)
                    song_title = response["entitiesByUniqueId"][
                        response["entityUniqueId"]
                    ]["title"]
                    song_artist = response["entitiesByUniqueId"][
                        response["entityUniqueId"]
                    ]["artistName"]
                    thumb = response["entitiesByUniqueId"][response["entityUniqueId"]][
                        "thumbnailUrl"
                    ]
                    yturl = response["linksByPlatform"]["youtube"]["url"]
                    ytdl_data = ytdl.extract_info(yturl, download=False)
                    url = ytdl_data["formats"][1]["url"]
                    title = song_title + " by " + song_artist
                    return (
                        url,
                        src,
                        thumb,
                        title,
                    )
                except:
                    return ()
        else:
            src = "youtube"
            ytdl_data = ytdl.extract_info(f"ytsearch:{args}", download=False)
            title = ytdl_data["entries"][0]["title"]
            url = ytdl_data["entries"][0]["formats"][1]["url"]
            thumb = ytdl_data["entries"][0]["thumbnail"]
            return (
                url,
                src,
                thumb,
                title,
            )


def songplayer(ctx, url):
    voice = ctx.channel.guild.voice_client
    guildid = TESTING_GUILD_ID
    player = FFmpegOpusAudio(url, **ffmpegOpts)
    after = lambda err: aftersong(guildid, err)
    try:
        voice.play(player, after=after)
    except Exception as e:
        return e
    return


async def ensure_voice(
    ctx,
):
    guild_id = TESTING_GUILD_ID
    voice = ctx.channel.guild.voice_client
    authorChannel = ctx.author.voice.channel if ctx.author.voice else None
    if authorChannel is None:
        embed = discord.Embed(
            title="You must be in a voice channel to use this.", color=colors["error"]
        )
        await ctx.send(embed=embed)
        return False
    else:
        if guild_id not in music_queue.keys():
            music_queue[guild_id] = []
        if voice is None:
            await ctx.author.voice.channel.connect()
            embed = discord.Embed(
                title="Connected to your voice channel.", color=colors["success"]
            )
            await ctx.send(embed=embed)
        elif ctx.author.voice.channel is not voice.channel:
            await voice.move_to(ctx.author.voice.channel)
            embed = discord.Embed(
                title="Inconsistency in bot's channel, moved to your voice channel.",
                color=colors["neutral"],
            )
            await ctx.send(embed=embed)
        await ctx.guild.change_voice_state(
            channel=ctx.author.voice.channel, self_mute=False, self_deaf=True
        )
        return True


def aftersong(guildid, err=None):
    guildid = TESTING_GUILD_ID
    try:
        ctx = music_queue[guildid][0][4]
    except IndexError:
        return
    nxt = next(ctx)
    if err is not None:
        embed = discord.Embed(
            title="Unable to play the next song.",
            description=str(e),
            color=colors["error"],
        )
        coro = ctx.send(embed=embed)
    else:
        if nxt is None:
            coro = ctx.send(
                embed=discord.Embed(
                    title="Queue ended.",
                    description="No next song to play, you can add a song to queue using the play command",
                    color=colors["error"],
                )
            )
        else:
            url, src, title = nxt[0], nxt[1], nxt[3]
            embed = discord.Embed(
                title="Playing Next", description="**" + title + "**", color=colors[src]
            )
            coro = ctx.send(embed=embed)

    fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    if nxt is not None:
        songplayer(ctx, url)
    try:
        fut.result()
    except Exception as e:
        print(e)
        pass


async def playsong(ctx, arg):
    if arg == ():
        embed = discord.Embed(
            title="Please enter the name of the song you want me to play.",
            description="I will look it up on youtube, you can even give me spotify or apple music links too",
            color=0xF54257,
        )
        await ctx.send(embed=embed)
        return
    check = await ensure_voice(ctx)
    if check is False:
        return
    guild_id = TESTING_GUILD_ID
    voice = ctx.channel.guild.voice_client
    ctxa = ctx
    if guild_id not in music_queue.keys():
        music_queue[guild_id] = []

    if voice.is_playing():
        embed = discord.Embed(
            title="A song is already being played, adding this one to the Queue",
            color=colors["neutral"],
        )
        message = await ctx.send(embed=embed)
        try:
            url, src, thumb, title, ctx = addsong(ctx, arg)
            embed = discord.Embed(
                title="A song is already being played, adding this one to the Queue",
                description="**" + title + "**",
                color=colors[src],
            )
            embed.set_thumbnail(url=thumb)
            await message.edit(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="Unable to play the song.",
                description=str(e),
                color=colors["error"],
            )
            await message.edit(embed=embed)
        return
    # try:
    url, src, thumb, title, ctx = addsong(ctxa, arg)
    songplayer(ctx, url)
    embed = discord.Embed(title=f"Now Playing", description=title, color=colors[src])
    embed.set_thumbnail(url=thumb)
    await ctx.send(embed=embed)


async def skip(ctx, position=0):
    check = await ensure_voice(ctx)
    if check is False:
        return
    if position != 0:
        remove(ctx, id=position)
        return
    voice = ctx.channel.guild.voice_client
    try:
        voice.stop()
        nxt = next(ctx)
        if nxt is None:
            await ctx.send(
                embed=discord.Embed(
                    title="Skipped the song.",
                    description="Queue is empty cannot proceed, add songs using the play/add command",
                    color=colors["success"],
                )
            )
        else:
            url, src, title = nxt[0], nxt[1], nxt[3]
            await ctx.send(
                embed=discord.Embed(
                    title="Skipped the song, Playing Next",
                    description="**" + title + "**",
                    color=colors[src],
                )
            )
            songplayer(ctx, url)
    except Exception as e:
        ctx.send(
            embed=discord.Embed(
                title="An Error Occured whilst trying to skip song",
                description=e,
                color=colors["error"],
            )
        )
        return


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


async def is_user_banned(ban_collection, user_id):
    result = ban_collection.find_one({"_id": user_id})
    return result is not None


async def is_user_kicked(kick_collection, user_id):
    result = kick_collection.find_one({"_id": user_id})
    return result is not None


def create_modmail_channel(interaction, mod_role_name, user_id, channel_name):
    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            read_messages=False, send_messages=False
        ),
        bot.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    moderator_role = get_mod_role_by_name(mod_role_name, guild)

    if moderator_role:
        overwrites[moderator_role] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        )
        return guild.create_text_channel(channel_name, overwrites=overwrites)


async def handle_server_user_modmail(interaction, user, mod_role_name):

    modmail_channel = await create_modmail_channel(
        user.id, channel_name=f"modmail-{user.id}"
    )

    await modmail_channel.send(
        f"Hey {user.mention}, thanks for contacting us! A moderator will be with you shortly if they choose to respond."
    )

    if mod_role_name:
        moderator_role = get_mod_role_by_name(mod_role_name, interaction.guild)
        if moderator_role:
            moderator_role = mod_role_name
            await modmail_channel.send(f"<@&{moderator_role.id}>")
    else:
        await modmail_channel.send(
            f"You did not select a specific category of mod you want to interact with."
        )


async def handle_banned_user_modmail(interaction, user, mod_role_name):

    modmail_channel = await create_modmail_channel(user.id, f"modmail-{user.id}")

    await modmail_channel.send(
        f"Hey {user.mention}, thanks for contacting us! You are currently banned from the server. A moderator will be with you shortly if they choose to respond."
    )

    if mod_role_name:
        moderator_role = get_mod_role_by_name(mod_role_name, interaction.guild)
        if moderator_role:
            moderator_role = mod_role_name
            await modmail_channel.send(f"<@&{moderator_role.id}>")
    else:
        await modmail_channel.send(
            f"You did not select a specific category of mod you want to interact with."
        )


async def handle_kicked_user_modmail(interaction, user, mod_role_name):

    modmail_channel = await create_modmail_channel(user.id, f"modmail-{user.id}")

    await modmail_channel.send(
        f"Hey {user.mention}, thanks for contacting us! You are currently kicked from the server. A moderator will be with you shortly if they choose to respond."
    )

    if mod_role_name:
        moderator_role = get_mod_role_by_name(mod_role_name, interaction.guild)
        if moderator_role:
            moderator_role = mod_role_name
            await modmail_channel.send(f"<@&{moderator_role.id}>")
    else:
        await modmail_channel.send(
            f"You did not select a specific category of mod you want to interact with."
        )


def get_mod_role_by_name(mod_role_name, guild):
    for role in guild.roles:
        if role.name.lower() == mod_role_name.lower():
            return role
    return None


# Anti-link functions


def strip_url(url):
    url = re.sub(r"^(?:https?|ftp)://", "", url)
    url = re.sub(r"/.*$", "", url)
    return url


# Bot events


@bot.event
async def on_member_join(member):
    role = member.guild.get_role(AUTO_ASSIGN_ROLE_ID)
    await member.add_roles(role)


@bot.event
async def on_command_completion(ctx):
    if ctx.command.name in (
        "play",
        "connect",
        "join",
        "next",
        "add",
        "p",
        "pause",
        "stop",
        "skip",
        "queue",
        "dc",
        "boot",
        "leave",
        "loopqueue",
        "lq",
        "r",
        "q",
        "resume",
        "disconnect",
    ):
        await ctx.message.delete()


@bot.event
async def on_dm(message):
    author = message.author
    guild = None

    if message.content.lower().startswith("/mod_mail"):
        is_banned = await is_user_banned(ban_collection, author.id)
        is_kicked = await is_user_kicked(kick_collection, author.id)

        if guild is not None and author in guild.members:
            await handle_server_user_modmail(message, author)
            return

        if is_banned or not guild:
            await handle_banned_user_modmail(message, author)
            return
        if is_kicked or not guild:
            await handle_kicked_user_modmail(message, author)
            return

        await author.send(
            "You are not currently in the server or banned/kicked. Mod Mail might be unavailable.",
            ephemeral=True,
        )


@bot.event
async def on_member_ban(member):

    await ban_collection.insert_one(
        {"_id": member.id, "action": "banned", "timestamp": datetime.now()}
    )


@bot.event
async def on_member_kick(member):

    await kick_collection.insert_one(
        {"_id": member.id, "action": "kicked", "timestamp": datetime.now()}
    )


@bot.event
async def on_ready():
    print(f"{bot.user} has logged in")


async def check_level_up(channel, message, currency_collection):
    query = {"_id": message.author.id}
    user = currency_collection.find_one(query)

    if not user:
        post = {"_id": message.author.id, "score": 0, "currency": 0, "level": 0}
        currency_collection.insert_one(post)
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


@bot.event
async def background_unban_task(interaction: discord.Interaction):
    delay, user_to_unban, guild = await unban_tasks.get()

    if delay <= 0:
        await interaction.guild.unban(user_to_unban)
        print(f"Unbanned user {user_to_unban} (scheduled task)")
    else:
        await unban_tasks.put((delay, user_to_unban, guild))

    await asyncio.sleep(5)


@bot.event
async def on_message(message):
    if message.author != bot.user:
        print(message.author, message.channel, message.content, message.embeds)
        await log_event(
            f"Message sent in {message.channel}", message.author, message.content
        )
        # Level and Currency System
        myquery = {"_id": message.author.id}
        if currency_collection.count_documents(myquery) == 0:
            if "" in str(message.content.lower()):
                post = {
                    "_id": message.author.id,
                    "score": 1,
                    "currency": 1,
                    "level": 1,
                }
                currency_collection.insert_one(post)
        else:
            if "" in str(message.content.lower()):
                query = {"_id": message.author.id}
                user = currency_collection.find(query)
                for result in user:
                    old_score = result["score"]
                    old_currency = result["currency"]
                score = old_score + 1
                level = score // 100
                currency = old_currency + 1
                currency_collection.update_one(
                    query,
                    {
                        "$set": {
                            "score": score,
                            "currency": currency,
                            "level": level,
                        }
                    },
                )
        await check_level_up(message.channel, message, currency_collection)
        await bot.process_commands(message)

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
        if message.author != bot.user:
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
        if message.author != bot.user:
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

    # auto-delete 10+ digits of numbers

    if author not in user_messages:
        user_messages[author.id] = []
    user_messages[author.id].append(message.content)

    potential_number = "".join(user_messages[author.id][-5:])
    if re.match(phone_number_regex, potential_number):
        await message.channel.delete_messages([message, user_messages[author.id][-2]])
        user_messages[author.id].pop()
        await message.channel.send(
            f"Hey {author.mention}, please avoid sharing phone numbers in the chat."
        )
        user_messages[author.id].clear()

    if len(user_messages[author.id]) > 6:
        user_messages[author.id] = user_messages[author.id][-6:]


@bot.event
async def on_message_delete(message):
    if message.author.id != bot.application_id:
        await log_event(
            f"Message Deleted from {message.channel.name}",
            message.author,
            message.content,
        )


@bot.event
async def on_message_edit(before, after):
    if before.author.id != bot.application_id and after.author.id != bot.application_id:
        channel_name = before.channel.name
        await log_event(
            f"Message Edited in {channel_name}",
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
                    log_message = f"{member.mention} (ID: {member.id}) stayed in {channel_name} for {delta.seconds} seconds."
                    await log_event(
                        "Voice Channel Left (Duration)", member, log_message
                    )

    if member.id == bot.user.id:
        return
    voice = discord.utils.get(bot.voice_clients, guild=member.guild)
    if voice is None:
        return
    voice_channel = voice.channel
    member_count = len(voice_channel.members)
    if member_count == 1:
        await asyncio.sleep(30)
        if member_count == 1:
            await voice.disconnect()
            guildid = member.guild.id
            ctx = music_queue[guildid][0][4]
            clear(ctx)
            embed = discord.Embed(
                title="Left voice channel, and cleared queue",
                description="No one else in the voice channel :/",
                color=colors["neutral"],
            )
            await ctx.send(embed=embed)


@bot.event
async def on_member_update(before, after):
    if before.id != bot.application_id and after.id != bot.application_id:
        if before.roles != after.roles:
            added_roles = [role for role in after.roles if role not in before.roles]
            removed_roles = [role for role in before.roles if role not in after.roles]
            log_message = f"Member Role Update: {after.mention} (ID: {after.id})\n"
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
    user = currency_collection.find_one(query)
    currency = user.get("currency", 0) if user else 0

    await interaction.send(f"You have {currency} currency", ephemeral=True)


@bot.slash_command(
    name="get_level",
    description="To show how many levels you gained",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
async def getLevels(interaction: discord.Interaction):
    query = {"_id": interaction.user.id}
    user = currency_collection.find_one(query)
    level = user.get("level", 0) if user else 0

    await interaction.send(f"You have reached level {level}", ephemeral=True)


@bot.slash_command(
    name="warn",
    description="Warns a user for breaking a rule.",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(kick_members=True)
async def warn_user(
    interaction: discord.Interaction, user: discord.Member, reason: str
):

    warning_threshold = 3

    warn_data = {
        "guild_id": interaction.guild.id,
        "user_id": user.id,
        "reason": reason,
        "warned_by": interaction.user.id,
        "warned_at": datetime.now(),
        "count": 1,
    }
    update_filter = {"guild_id": interaction.guild.id, "user_id": user.id}
    update_ops = {"$inc": {"count": 1}}

    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to warn.", ephemeral=True
        )
        return

    if user == bot.user:
        await interaction.response.send_message(
            "You cannot warn the bot.", ephemeral=True
        )
        return

    try:
        query = {"user_id": user.id}
        warned_user = warn_collection.find_one(query)
        if warned_user:
            updated_doc = warn_collection.update_one(
                update_filter, update_ops, upsert=True
            )
        else:
            warn_collection.insert_one(warn_data)
            warned_user = warn_collection.find_one(query)
        warning_count = warned_user.get("count", 0)

        if warning_count > warning_threshold:
            try:
                await interaction.guild.ban(user)
                await interaction.response.send_message(
                    f"{user.mention} has crossed the warning threshold and has been banned.",
                    ephemeral=True,
                )
            except discord.HTTPException as e:
                print(f"Error banning user: {e}")
                await interaction.response.send_message(
                    f"Failed to ban {user.mention}. Insufficient permissions or other errors.",
                    ephemeral=True,
                )
                return
        else:
            await interaction.response.send_message(
                f"Warning has been sent.",
                ephemeral=True,
            )

        await user.send(
            f"You have been warned in {interaction.guild.name} for: {reason}. Meeting {warning_threshold} warnings threshold will ban you."
        )
    except discord.HTTPException as e:
        print(f"Failed to send DM to user: {e}")
        await interaction.response.send_message(
            f"Failed to warn {user.mention}. User might have DMs disabled.",
            ephemeral=True,
        )
        return

    await interaction.channel.send(f"{user.mention} has been warned for: {reason}")


@bot.slash_command(
    name="kick",
    description="Kick a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(kick_members=True)
async def memberKick(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption("kick", "Kick a user from server"),
    reason: str = discord.SlashOption(
        "reason", "Provide a reason to kick the selected user"
    ),
):
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to kick.", ephemeral=True
        )
        return
    await interaction.guild.kick(user, reason=reason)
    await interaction.send(f"{user} has been kicked", ephemeral=True)


@bot.slash_command(
    name="ban",
    description="Ban a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(ban_members=True)
async def memberBan(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption("ban", "Ban a user from server"),
    delete_message_days: int = discord.SlashOption(
        "delete_message_days",
        "Delete this user's previous messages up to",
        required=False,
    ),
    reason: str = discord.SlashOption(
        "reason", "Provide a reason to ban the selected user"
    ),
):
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to ban.", ephemeral=True
        )
        return
    await interaction.guild.ban(
        user, delete_message_days=delete_message_days, reason=reason
    )
    await interaction.send(f"{user} has been banned", ephemeral=True)


@bot.slash_command(
    name="temp_ban",
    description="Temporarily ban a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(ban_members=True)
async def memberTempBan(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption("ban", "ban a user from server"),
    duration: int = discord.SlashOption(
        name="duration",
        description="Ban duration in days (default: 10 days)",
        required=False,
    ),
    delete_message_days: int = discord.SlashOption(
        "delete_message_days",
        "delete this user's previous messages upto",
        required=False,
    ),
    reason: str = discord.SlashOption(
        "reason", "provide a reason to ban the selected user"
    ),
):
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to ban temporarily.", ephemeral=True
        )
        return
    guild = interaction.guild
    if not duration:
        duration = 10

    unban_time = datetime.now(datetime.timezone.utc) + timedelta(days=duration)

    reason_with_time = (
        f"Temporarily banned {user} (unban at {unban_time.strftime('%H:%M:%S %Z')})"
    )
    if reason:
        reason_with_time += f" Reason: {reason}"
    await user.ban(reason=reason_with_time)

    await schedule_unban_task(user, guild, unban_time)

    await interaction.response.send_message(
        f"Temporarily banned {user.name} for {duration} day(s)."
    )

    await guild.ban(
        user, duration, delete_message_days=delete_message_days, reason=reason
    )
    await interaction.send(f"{user} has been banned temporarily.", ephemeral=True)


@bot.slash_command(
    name="unban",
    description="Unban a person from server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(ban_members=True)
async def memberUnban(
    interaction: discord.Interaction,
    user: str = discord.SlashOption("unban", "Unban a user from server"),
    reason: str = discord.SlashOption(
        "reason", "Provide a reason to unban the selected user"
    ),
):
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to unban.", ephemeral=True
        )
        return
    await interaction.guild.unban(discord.Object(id=user), reason=reason)
    await interaction.send(f"{user} has been unbanned", ephemeral=True)


@bot.slash_command(
    name="timeout",
    description="Timeout/Mute a person in server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_permissions(mute_members=True)
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
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to timeout/mute.", ephemeral=True
        )
        return
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
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to change nickname.", ephemeral=True
        )
        return
    await user.edit(nick=nickname)
    await interaction.send(f"Nickname of {user} has been changed.", ephemeral=True)


@bot.slash_command(
    name="give_admin",
    description="Give Administrator Permissions to a person in server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_guild_permissions(administrator=True)
async def GiveAdmin(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "Select a user to give admin perms in server"
    ),
    admin_role: discord.Role = discord.SlashOption(
        "admin_role", "Select the role with admin perms."
    ),
):
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to give admin perms to.", ephemeral=True
        )
        return
    await user.edit(roles=[admin_role])
    await interaction.send(
        f"Administrator Permissions have been given to {user}", ephemeral=True
    )
    await interaction.channel.send(
        f"{user.mention} You have recieved Administrator Permissions from the Owner."
    )


@bot.slash_command(
    name="change_roles",
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
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to change roles.", ephemeral=True
        )
        return
    await user.edit(roles=[manage_roles])
    await interaction.send(f"Roles have been updated for {user}", ephemeral=True)


@bot.slash_command(
    name="ping_role",
    description="Pings a role in the server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(administrator=True)
@application_checks.has_guild_permissions(manage_roles=True)
async def pingRole(
    interaction: discord.Interaction,
    role: discord.Role = discord.SlashOption("role", "Select a role to ping"),
    message: str = discord.SlashOption("message", "Optional message to be included"),
):
    if role is None:
        await interaction.response.send_message(
            "Please specify a valid role to ping.", ephemeral=True
        )
        return
    ping_message = f"<@&{role.id}>"
    if message:
        ping_message += f"{message}"

    await interaction.response.send_message(ping_message)


@bot.slash_command(
    name="mod_mail",
    description="File a ticket to moderators for support.",
)
async def open_modmail(
    interaction: discord.Interaction,
    mod_role_name: discord.Role = discord.SlashOption(
        "category", "Select a category of support"
    ),
):
    user = interaction.user
    guild = interaction.guild
    query = {"_id": interaction.user.id}
    banned_user = ban_collection.find_one(query)
    kicked_user = kick_collection.find_one(query)
    banned_members = banned_user.get("_id") == interaction.user.id
    kicked_members = kicked_user.get("_id") == interaction.user.id

    if guild is not None and user in guild.members:
        await handle_server_user_modmail(interaction, user, mod_role_name)
        return

    if user in banned_members:
        await handle_banned_user_modmail(interaction, user, mod_role_name)
        return

    if user in kicked_members:
        await handle_kicked_user_modmail(interaction, user, mod_role_name)
        return

    await interaction.response.send_message(
        "You are not currently in the server or banned/kicked. Mod Mail might be unavailable.",
        ephemeral=True,
    )


@bot.slash_command(
    name="create_vc",
    description="Create a private voice channel in the server.",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
async def createVoice(
    interaction: discord.Interaction,
    create_voice: str = discord.SlashOption("name", "Give a name for the Text Channel"),
    user_limit: int = discord.SlashOption(
        "limit", "Set a limit to how many users can join the Voice Channel"
    ),
):
    query = {"_id": interaction.user.id}
    user = currency_collection.find_one(query)
    currency = user.get("currency", 0) if user else 0
    guild = interaction.guild
    if currency >= 10:
        currency_collection.update_one(query, {"$set": {"currency": currency - 10}})

        voice_channel = await guild.create_voice_channel(
            name=create_voice, user_limit=user_limit
        )

        await interaction.response.send_message(
            f"{voice_channel.name} voice channel has been created with a limit of {user_limit} users.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "You do not have enough currency to create a voice channel.", ephemeral=True
        )


@bot.slash_command(
    name="find_in_vc",
    description="Find in which VC a user is in.",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
async def findInVc(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "Select a user to find for in a VC"
    ),
):
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to find.", ephemeral=True
        )
        return

    guild = interaction.guild

    for voice_channel in guild.voice_channels:
        for member in voice_channel.members:
            if member == user:
                await interaction.response.send_message(
                    f"Found {user.name} in voice channel: {voice_channel.name}",
                    ephemeral=True,
                )
                return
    await interaction.response.send_message(
        f"{user.name} is not currently in a voice channel.", ephemeral=True
    )


@bot.slash_command(
    name="vc_drag",
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
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to drag.", ephemeral=True
        )
        return
    await user.move_to(change_vc)
    await interaction.send(f"{user} has been dragged to {change_vc}", ephemeral=True)


@bot.slash_command(
    name="request_vc_drag",
    description="Ask a mod for a drag request.",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
async def dragMe(
    interaction: discord.Interaction,
    role: discord.Role = discord.SlashOption(
        "mod_role", "Select a mod role to help you drag into a VC"
    ),
    change_vc: discord.VoiceChannel = discord.SlashOption(
        "drag", "Change VC for the selected user"
    ),
):

    if interaction.user.voice:
        if interaction.user.voice.channel == change_vc:
            await interaction.response.send_message(
                "You're already in the same voice channel as that user!", ephemeral=True
            )
            return

        new_request = {
            "requester_id": interaction.user.id,
            "role_id": role.id,
            "requested_channel_id": change_vc.id,
            "timestamp": datetime.now(),
        }
        drag_request_collection.insert_one(new_request)

        mod_channel = bot.get_channel(MOD_CHANNEL_ID)
        await interaction.response.send_message(
            f"You requested to be dragged to {change_vc.name} voice channel. Please wait for a moderator's approval.",
            ephemeral=True,
        )
        await mod_channel.send(
            f"{role.mention}.{interaction.user.name} has requested to be dragged to {change_vc.name} voice channel. Approve with `/acceptdrag {interaction.user.name}` or deny with `/denydrag {interaction.user.name}`."
        )
    else:
        await interaction.response.send_message(
            "You're not in any voice channels.", ephemeral=True
        )


@bot.slash_command(
    name="accept_vc_drag",
    description="Move a user to a voice channel (requires Move Members permission)",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(manage_channels=True)
@application_checks.has_guild_permissions(move_members=True)
async def acceptdrag(
    interaction: discord.Interaction,
    user: discord.Member,
    change_vc: discord.VoiceChannel = discord.SlashOption(
        "vc", "Select a voice channel to move the user to"
    ),
):
    request_doc = drag_request_collection.find_one({"requester_id": user.id})
    if not request_doc:
        await interaction.response.send_message(
            f"{user.name} has no pending drag request."
        )
        return

    requester_user_id = request_doc["requester_id"]
    requester_user = interaction.guild.get_member(requester_user_id)

    if not requester_user:
        await interaction.response.send_message(
            f"Could not find the user who requested to be dragged {change_vc.name}voice channel.",
            ephemeral=True,
        )
        drag_request_collection.delete_one(
            {"requester_id": request_doc["requester_id"]}
        )
        return

    try:
        await requester_user.move_to(change_vc)
        await interaction.response.send_message(
            f"{requester_user.name} has been dragged to {change_vc.name}.",
            ephemeral=True,
        )
        await interaction.channel.send(
            f"{requester_user.mention} You have been dragged to {change_vc.name}."
        )
        drag_request_collection.delete_one(
            {"requester_id": request_doc["requester_id"]}
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(
            f"Failed to move {requester_user.name} to {change_vc.name}. (Error: {e})",
            ephemeral=True,
        )


@bot.slash_command(
    name="deny_vc_drag",
    description="Deny a user's drag request (requires Move Members permission)",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_permissions(manage_channels=True)
@application_checks.has_guild_permissions(move_members=True)
async def denydrag(interaction: discord.Interaction, user: discord.Member):
    request_doc = drag_request_collection.find_one({"requester_id": user.id})
    if not request_doc:
        await interaction.response.send_message(
            f"{user.name} has no pending drag request."
        )
        return

    drag_request_collection.delete_one({"requester_id": request_doc["requester_id"]})
    await interaction.response.send_message(
        f"{user.name}'s drag request has been denied.", ephemeral=True
    )
    await interaction.channel.send(f"{user.mention} Your drag request has been denied.")


@bot.slash_command(
    name="help",
    description="Shows a list of all slash commands in the server",
    guild_ids=[config.getint("GUILD", "testing_guild_id")],
)
@commands.has_guild_permissions(administrator=True)
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="My Commands")

    ban_desc = "To ban a user from the server."
    # tempBan_desc = "To ban a user temporarily from the server."
    # unban_desc = "To unban a user from the server."
    kick_desc = "To kick a user from the server."
    warn_desc = "To warn a user in the server."
    timeout_desc = "To timeout/mute a user in the server."
    nick_desc = "To change nickname of a user in the server."
    giveAdmin_desc = "To give Administrator Permissions to a user in the server."
    roles_desc = "To change roles of a user in the server."
    ping_desc = "To ping a role in the server."
    drag_desc = "To drag a user between VCs in the server."
    dragReq_desc = "To send a drag request for VCs in the server."
    dragAccept_desc = "To accept a drag request of a user in the server."
    dragDeny_desc = "To deny a drag request of a user in the server."
    findVc_desc = "To find which VC a user is in."
    modMail_desc = "To open a modmail ticket for support from moderators."
    currency_desc = "To show how much currency you have."
    level_desc = "To show how many levels you have gained."
    createVoice_desc = "To create a private voice channel using 10 currency."
    play_desc = "To play/add songs into the music bot."
    pause_desc = "To pause music using the music bot."
    resume_desc = "To resume music using the music bot."
    skip_desc = "To skip music using the music bot."
    disconnect_desc = "To disconnect the music bot."

    embed.add_field(name="`/ban`", value=ban_desc, inline=False)
    # embed.add_field(name="`/temp_ban`", value=tempBan_desc, inline=False)
    # embed.add_field(name="`/unban`", value=unban_desc, inline=False)
    embed.add_field(name="`/kick`", value=kick_desc, inline=False)
    embed.add_field(name="`/warn`", value=warn_desc, inline=False)
    embed.add_field(name="`/timeout`", value=timeout_desc, inline=False)
    embed.add_field(name="`/nickname`", value=nick_desc, inline=False)
    embed.add_field(name="`/give_admin`", value=giveAdmin_desc, inline=False)
    embed.add_field(name="`/change_roles`", value=roles_desc, inline=False)
    embed.add_field(name="`/ping_role`", value=ping_desc, inline=False)
    embed.add_field(name="`/vc_drag`", value=drag_desc, inline=False)
    embed.add_field(name="`/request_vc_drag`", value=dragReq_desc, inline=False)
    embed.add_field(name="`/accept_vc_drag`", value=dragAccept_desc, inline=False)
    embed.add_field(name="`/deny_vc_drag`", value=dragDeny_desc, inline=False)
    embed.add_field(name="`/mod_mail`", value=modMail_desc, inline=False)
    embed.add_field(name="`/find_in_vc`", value=findVc_desc, inline=False)
    embed.add_field(name="`/get_currency`", value=currency_desc, inline=False)
    embed.add_field(name="`/get_level`", value=level_desc, inline=False)
    embed.add_field(name="`/create_voice`", value=createVoice_desc, inline=False)
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


async def play_queue(ctx, url):
    global music_queue
    global disconnect_now
    global is_looping

    while music_queue:
        url = music_queue.popleft()

        try:
            source = discord.FFmpegAudio(url)
            ctx.voice_client.play(source)
            await source.wait_for_end()

            if is_looping and music_queue:
                music_queue.extend(music_queue)

        except Exception as e:
            print(f"Error playing song: {e}")
            await ctx.send(f"An error occurred while playing {url}. Skipping...")
            await asyncio.sleep(5)

    if not music_queue:
        await ctx.voice_client.disconnect()
        music_queue = deque()


# Music bot commands


@bot.command(name="play", aliases=["connect", "join", "next", "add", "p"])
async def command_play(ctx, *arg):
    await playsong(ctx, arg)


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


@bot.command(name="disconnect", aliases=["dc", "boot", "stop", "leave", "end"])
async def command_stop(ctx):
    voice = ctx.channel.guild.voice_client
    if voice is not None:
        await clear(ctx)
        await voice.disconnect()
        embed = discord.Embed(
            title="Stopped playing music, and cleared song queue",
            color=colors["success"],
        )
    else:
        embed = discord.Embed(title="Bot not in a voice channel", color=colors["error"])
    await ctx.send(embed=embed)


@bot.command(name="skip")
async def command_skip(ctx, pos: int = 0):
    await skip(ctx, pos)


is_looping = False


@bot.command(name="loop", aliases=["loopqueue", "lq"])
async def loop(ctx):

    global is_looping
    is_looping = not is_looping
    await ctx.send(f"Song Looping: {'Enabled' if is_looping else 'Disabled'}")


@bot.command(name="queue", aliases=["q", "list", "l"])
async def command_queue(ctx):
    guild_id = TESTING_GUILD_ID
    if guild_id not in music_queue.keys():
        music_queue[guild_id] = []
    np = await now_playing(ctx)
    if np != None:
        description = "**Now playing:** " + np[3]
    else:
        description = ""
    embed = discord.Embed(
        title="Song Queue", description=description, color=colors["neutral"]
    )
    if len(music_queue[guild_id]) > 1:
        for i in music_queue[guild_id]:
            if i == music_queue[guild_id][0]:
                continue
            id = music_queue[guild_id].index(i)
            embed.add_field(
                name=str(id) + ". " + i[3],
                value=f"-------------------------------",
                inline=False,
            )
    else:
        embed.add_field(
            name="No songs in queue",
            value="songs are added automatically to queue when there is already a song playing",
            inline=False,
        )
    await ctx.send(embed=embed)


@bot.command(
    name="now_playing", aliases=["np", "current_song", "currently_playing", "cs", "cp"]
)
async def now_playing(ctx):
    guild_id = TESTING_GUILD_ID
    if TESTING_GUILD_ID not in music_queue.keys():
        music_queue[guild_id] = []
    voice = ctx.channel.guild.voice_client
    if voice is None:
        return None
    if voice.is_playing():
        return music_queue[guild_id][0]


@bot.command(name="clear", aliases=["clear_queue", "cq"])
async def clear(ctx):
    guild_id = TESTING_GUILD_ID
    music_queue[guild_id] = []
    await ctx.send("Queue has been cleared.")
    return None


@bot.command(name="remove", aliases=["remove_song", "rm"])
async def remove(ctx, id):
    print(type(id))
    if TESTING_GUILD_ID not in music_queue.keys():
        music_queue[TESTING_GUILD_ID] = []
    await music_queue[TESTING_GUILD_ID].pop(id)
    if id is None:
        await ctx.send("Give a number as to which song to delete.")
    await ctx.send("Song has been removed.")
    return None


bot.run(config.get("BOT", "auth_token"))
