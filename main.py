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
import threading
import signal
from discord.ext.commands import has_permissions, MissingPermissions, BadArgument
from youtube_dl import YoutubeDL
from pymongo import MongoClient, ReturnDocument
from nextcord import SelectOption
from nextcord import FFmpegOpusAudio
from nextcord.ext import application_checks, commands
from nextcord.ui import Button, View, StringSelect
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

bot = commands.Bot(
    # command_prefix="c.",
    intents=intents,
    case_insensitive=False,
)
exit_event = threading.Event()

master_vc_user = {}

member_voice_times = {}
message_cooldowns = {}
user_cooldowns = {}
user_messages = {}
phone_number_regex = (
    r"^\s*(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})(?: *x(\d+))?\s*$"
)
unban_tasks = []

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
member_leave_collection = db[config.get("DATABASE", "member_leave_collection")]
warn_collection = db[config.get("DATABASE", "warn_collection")]

TESTING_GUILD_ID = config.getint("GUILD", "testing_guild_id")
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
MAIL_CUSTOMER_ID = config.getint("GUILD", "mail_customer_id")


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


async def is_user_removed(member_leave_collection, user_id):
    result = member_leave_collection.find_one({"_id": user_id})
    return result is not None


# Anti-link functions


def strip_url(url):
    url = re.sub(r"^(?:https?|ftp)://", "", url)
    url = re.sub(r"/.*$", "", url)
    return url


def unban_user(bot_token, guild_id, user_id):
    url = f"https://discord.com/api/v10/guilds/{guild_id}/bans/{user_id}"
    headers = {
        "Authorization": f"Bot {bot_token}",
    }

    response = requests.delete(url, headers=headers)
    
    if response.status_code == 204:
        print(f"User {user_id} has been unbanned from guild {guild_id}.")
    else:
        print(f"Failed to unban user {user_id}. Status code: {response.status_code}")
        print("Response:", response.json())


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
async def on_member_remove(member):
    member_leave = member_leave_collection.find_one(
        {"_id": member.id}
    )
    if member_leave is None:
        member_leave_collection.insert_one(
            {"_id": member.id, "action": "removed", "timestamp": datetime.now()}
        )
    else:
        member_leave_collection.update_one({"_id": member.id},
            {"$set": {"action": "removed", "timestamp": datetime.now()} }
        )


@bot.event
async def on_ready():
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.listening,
        ),
    )
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
            f"Congratulations, {log_message}! You now have {currency} unit{'s' if  currency > 1 else ''} of currency!"
        )


async def schedule_unban_task(
    user_to_unban, guild, unban_time
):

    task = (unban_time, user_to_unban, guild)

    unban_tasks.append(task)
    print(f"User {user_to_unban} scheduled for unban at {unban_time}")

def signal_handler(signum, frame):
    exit_event.set()

def background_unban_task(bot):
    while True:
        if unban_tasks:
            unban_time, user_to_unban, guild = unban_tasks[0]
            delta = unban_time - datetime.now(timezone.utc)
            guild_id = bot.guilds[0].id
            user_id = user_to_unban.id
            bot_token = config.get("BOT", "auth_token")
            delay = max(delta.total_seconds(), 0)
            unban_tasks.pop()
            
            if delay <= 0:
                unban_user(bot_token, guild_id, user_id)
                print(f"Unbanned user {user_to_unban} (scheduled task)")
            else:
                unban_tasks.append((unban_time, user_to_unban, guild))

        time.sleep(5)

        if exit_event.is_set():
            break


@bot.event
async def on_message(message):
    if message.author != bot.user:
        try:
            gd = await bot.fetch_guild(TESTING_GUILD_ID)
            category1 = bot.get_channel(1233785738961879071)

            #### TICKET CLOSE FUNCTION ####
            if (
                message.channel in category1.channels
                and message.channel.id != 1233059905812955198
                and message.author.id != 1221737230285144095
                and message.content == "c.close"
            ):
                category = bot.get_channel(1233785738961879071)
                ch = await bot.fetch_channel(1233059905812955198)
                id = message.channel.topic
                usr = await bot.fetch_user(id)

                await message.channel.send("CLOSING TICKET ...")
                await usr.send(
                    f"**Greetings {usr.name}**\n```Your Ticket has been closed by our moderation team. If you want to contact us again , message in this channel once again. Note that, we don't accept any sort of trolling.```\n**Thank you**"
                )
                embed = discord.Embed(
                    title="TICKET CLOSED",
                    description=f"Ticket created by {usr.name} is closed by {message.author.name}.",
                    color=0xFF0000,
                )
                embed2 = discord.Embed(
                    title="TICKET CLOSED",
                    description=f"Ticket created by {usr.name} is closed.",
                    color=0xFF0000,
                )
                await ch.send(embed=embed)
                await asyncio.sleep(3)
                await usr.send(embed=embed2)
                await message.channel.delete()
                print("ticket close function")

            #### MODERATOR REPLY FUNCTION ####
            if (
                message.channel in category1.channels
                and message.channel.id != 1233059905812955198
                and message.author.id != 1221737230285144095
                and message.content != "c.close"
            ):
                usrid = message.channel.topic
                usr = await bot.fetch_user(usrid)

                if message.content == None:
                    msg = "None"
                else:
                    msg = message.content

                embed6 = discord.Embed(title="Message from TEAM", description=f"{msg}")
                await usr.send(f"{msg}")
                urls = []
                for att in message.attachments:
                    for i in range(len(urls)):
                        urls[i].append(att.url)
                    embed7 = discord.Embed(title="Attachment", color=0x75E6DA)
                    embed7.set_image(url=f"{urls[0]}")
                    await usr.send(embed=embed7)

            if message.channel.type == discord.ChannelType.private:
                if message.author.id != 1221737230285144095:

                    #### CHECKING IF USER HAS ALREADY CREATED A TICKET ####
                    topics = []
                    a = None

                    for mail_channel in category1.channels:
                        topics.append(mail_channel.topic)
                        if mail_channel.topic == str(message.author.id):
                            a = mail_channel.id

                    if f"{message.author.id}" in topics:
                        chnl = await bot.fetch_channel(a)
                        if message.content == None:
                            msg = "None"
                        else:
                            msg = message.content
                        embed3 = discord.Embed(title=f"Message from {message.author.name}", description=f"{msg}")
                        await chnl.send(embed=embed3)
                        urls = []
                        for att in message.attachments:
                            print("urls.append(att.url) the 2nd")
                            urls.append(att.url)
                        embed4 = discord.Embed(title="Attachment", color=0x75E6DA)
                        if urls:
                            embed4.set_image(url=f"{urls[0]}")
                            await chnl.send(embed=embed4)

                    else:
                        options_select = [SelectOption(label="Text Abuse", description=""),
                                          SelectOption(label="VC Abuse", description=""),
                                          SelectOption(label="Ban/Kick Appeal", description=""),
                                          SelectOption(label="Timeout Appeal", description=""),
                                        ]

                        select_menu = StringSelect(
                            placeholder="Select a category of support",
                            min_values=1,
                            max_values=1,
                            options=options_select,
                        )

                        async def select_cat(interaction: discord.Interaction):
                            print("CREATING TEXT CHANNEL")
                            ### CREATING TEXT CHANNEL ###

                            m1 = await gd.create_text_channel(
                                f"modmail-{message.author.name}",
                                category=category1,
                                topic=f"{message.author.id}",
                            )

                            ### SENDING USER A DM ###
                            embed1 = discord.Embed(
                                title=f"Greetings {message.author.name}",
                                description="```New ticket has been created for you, send your messages in my DM, which will be sent to our Moderation team and they will respond to you soon.\n\nNote the following things:\n1) Emotes wont be visible to mods.\n2) If you have to send images send one by one.\n3) Make sure you dont send nsfw content or swear during the course of help.\n4) You cannot close a ticket, since there might be a chance of re-opening your ticket .\n5) Be respectful and follow discord TOS.\n6) The following messages will be from a MOD. ```\n**Thank you**",
                                color=0x00FF00,
                            )

                            await message.author.send(embed=embed1)

                            ### SEND TICKET CHANNEL A REMOTE MESSAGE FOR CLOSE ETC ###

                            embed2 = discord.Embed(
                                title=f"TICKET CREATED for {select_menu.values[0]}",
                                description="Hey Mods \n```New ticket created,\nRemember that whatever you send in this channel henceforth will be sent to the user who created the ticket.```\n**Thank you**",
                                color=0xFF0000,
                            )

                            timestamp = datetime.now()
                            embed5 = discord.Embed(color=0xF1C0B9)
                            embed5.add_field(
                                name="**USER INFORMATION**",
                                value=f'```USER NAME - {message.author.name}\n\nUSER ACCOUNT AGE - {round((time.time() - message.author.created_at.timestamp())/86400)} days\n\nTIME OF CREATION - {timestamp.strftime(r"%I:%M %p") } ```',
                            )

                            await m1.send(embed=embed2)
                            await m1.send(embed=embed5)

                            ### BOT LOGS ### WHERE THE LOGGINGS WILL TAKE PLACE

                            ch = await bot.fetch_channel(1233059905812955198)

                            embed = discord.Embed(
                                title=f"TICKET CREATED for {select_menu.values[0]}",
                                description=f"New ticket created by user {message.author.name} for support in {select_menu.values[0]} category, [CLICK ME](https://discord.com/channels/{gd.id}/{m1.id}) to access ticket",
                                color=0x00FF00,
                            )

                            await ch.send(embed=embed)

                        select_menu.callback = select_cat
                        view = View()
                        view.add_item(select_menu)

                        await message.author.send(
                            "Please select a category for your message:", view=view
                        )

        except Exception as e:
            print(e)

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
                user = currency_collection.find_one(query)
                old_score = user.get("score", 0)
                old_currency = user.get("currency", 0)
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
    # print(user_messages)

    potential_number = "".join(user_messages[author.id][-2:1])
    # print(potential_number)

    if len(user_messages[author.id]) > 2:
        if re.match(phone_number_regex, potential_number):
            await message.channel.delete([message, user_messages[author.id][-2:1]])
            user_messages[author.id].pop()
            await message.channel.send(
                f"Hey {author.mention}, please avoid sharing phone numbers in the chat."
            )
            user_messages[author.id].clear()

    if len(user_messages[author.id]) > 3:
        user_messages[author.id] = user_messages[author.id][-3:1]


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
            channel_name = (
                after.channel.mention if after.channel else before.channel.mention
            )

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
    name="get-currency",
    description="To show how much currency you have",
    guild_ids=[TESTING_GUILD_ID],
)
async def getCurrency(interaction: discord.Interaction):
    query = {"_id": interaction.user.id}
    user = currency_collection.find_one(query)
    currency = user.get("currency", 0) if user else 0

    await interaction.response.send_message(
        f"You have {currency} currency", ephemeral=True
    )


@bot.slash_command(
    name="get-level",
    description="To show how many levels you gained",
    guild_ids=[TESTING_GUILD_ID],
)
async def getLevels(interaction: discord.Interaction):
    query = {"_id": interaction.user.id}
    user = currency_collection.find_one(query)
    level = user.get("level", 0) if user else 0

    await interaction.response.send_message(
        f"You have reached level {level}", ephemeral=True
    )


@bot.slash_command(
    name="leaderboard",
    description="To show the leaderboard of the server.",
    guild_ids=[TESTING_GUILD_ID],
)
async def leaderboard(interaction: discord.Interaction):
    query = {"_id": interaction.user.id}
    leaderboard_data = currency_collection.find().sort("score", -1)
    message = "**Leaderboard:**\n"
    position = 1
    for document in leaderboard_data:
        user_id = document["_id"]
        user = interaction.guild.get_member(user_id)
        if user is None:
            currency_collection.delete_one({"_id": user_id})
            continue
        score = document["score"]
        message += f"{position}. {user.name}: {score}\n"
        position += 1

    await interaction.response.send_message(
        message, ephemeral=True
    )


@bot.slash_command(
    name="warn",
    description="Warns a user for breaking a rule.",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(kick_members=True)
async def warn_user(
    interaction: discord.Interaction, user: discord.Member, reason: str
):

    warning_threshold = 5

    warn_data = {
        "guild_id": interaction.guild.id,
        "user_id": user.id,
        "reason": reason,
        "warned_by": interaction.user.id,
        "warned_at": datetime.now(),
        "count": 1,
    }
    update_filter = {"guild_id": interaction.guild.id, "user_id": user.id}
    update_ops = {"$set": {"reason": reason}, "$inc": {"count": 1}}

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
                await user.send(f"You have been banned from {interaction.guild.name} for: {reason}. And for crossing {warning_threshold} warnings threshold.")
                await interaction.guild.ban(user)
                warn_collection.delete_one(query)
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
            await user.send(f"You have been warned in {interaction.guild.name} for: {reason}. Crossing {warning_threshold} warnings threshold will ban you.")

        
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
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(kick_members=True)
async def memberKick(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption("kick", "Kick a user from server"),
    reason: str = discord.SlashOption(
        name="reason", description="Provide a reason to kick the selected user", required=False
    ),
):
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to kick.", ephemeral=True
        )
        return
    if reason is None:
        reason = "no reason provided"
    await interaction.guild.kick(user, reason=reason)
    await interaction.send(f"{user} has been kicked: {reason}", ephemeral=True)


@bot.slash_command(
    name="ban",
    description="Ban a person from server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(ban_members=True)
async def memberBan(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption("ban", "Ban a user from server"),
    reason: str = discord.SlashOption(
        name="reason", description="Provide a reason to ban the selected user"
    ),
    delete_message_days: int = discord.SlashOption(
        name="delete-message-days",
        description="Delete this user's previous messages up to",
        required=False,
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
    name="temp-ban",
    description="Temporarily ban a person from server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(ban_members=True)
async def tempBan(
    interaction: discord.Interaction,
    user: discord.User = discord.SlashOption(
        name="temp-ban", description="temporarily ban a user from server"
    ),
    reason: str = discord.SlashOption(
        name="reason", description="provide a reason to ban the selected user", required=False,
    ),
    duration: int = discord.SlashOption(
        name="duration",
        description="Ban duration in days (default: 10 days)",
        required = False,
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

    unban_time = datetime.now(timezone.utc) + timedelta(seconds=duration)

    reason_with_time = (
        f"Temporarily banned {user} (unban at {unban_time.strftime('%H:%M:%S %Z')})"
    )
    if reason:
        reason_with_time += f" Reason: {reason}"
        await interaction.guild.ban(user, reason=reason_with_time)
    else:
        await interaction.guild.ban(user, reason=None)

    await schedule_unban_task(user, guild, unban_time)
    await interaction.response.send_message(
        f"Temporarily banned {user.name} for {duration} day(s)."
    )
    await interaction.send(f"{user} has been banned temporarily.", ephemeral=True)


@bot.slash_command(
    name="unban",
    description="Unban a person from server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(ban_members=True)
async def memberUnban(
    interaction: discord.Interaction,
    user: str = discord.SlashOption("unban", "Unban a user from server"),
    reason: str = discord.SlashOption(
        name="reason", description="Provide a reason to unban the selected user"
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
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(mute_members=True)
async def memberMute(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        name="user", description="Timeout a user in minutes in server"
    ),
    timeout: int = discord.SlashOption(
        name="timeout", description="Provide an amount of time to mute in minutes"
    ),
    reason: str = discord.SlashOption(
        name="reason", description="Provide a reason to timeout the selected user"
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
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_guild_permissions(manage_nicknames=True)
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
    name="give-admin",
    description="Give Administrator Permissions to a person in server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
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
    name="add-roles",
    description="Manage roles of a person in server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
async def addRoles(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "Select a user to manage their roles in server"
    ),
    add_roles: discord.Role = discord.SlashOption(
        "roles", "Add roles for the selected user"
    ),
):
    if add_roles.position > interaction.guild.me.top_role.position:
        await interaction.response.send_message(
            "I can't add roles higher than my own position!", ephemeral=True
        )
        return
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to change roles.", ephemeral=True
        )
        return
    if add_roles.position < interaction.user.top_role.position:
        await user.add_roles(add_roles)
        await interaction.response.send_message(
            f"Role {add_roles} has been added to {user}.", ephemeral=True
        )
        return
    else:
        await interaction.response.send_message(
            "You cannot add roles higher than or equal to your own.", ephemeral=True
        )


@bot.slash_command(
    name="remove-roles",
    description="Manage roles of a person in server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
async def removeRoles(
    interaction: discord.Interaction,
    user: discord.Member = discord.SlashOption(
        "user", "Select a user to manage their roles in server"
    ),
    remove_roles: discord.Role = discord.SlashOption(
        "roles", "Remove roles for the selected user"
    ),
):
    if remove_roles.position > interaction.guild.me.top_role.position:
        await interaction.response.send_message(
            "I can't add roles higher than my own position!", ephemeral=True
        )
        return
    if user is None:
        await interaction.response.send_message(
            "Please specify a valid user to change roles.", ephemeral=True
        )
        return
    if remove_roles.position < interaction.user.top_role.position:
        await user.remove_roles(remove_roles)
        await interaction.response.send_message(
            f"Role {remove_roles} has been removed from {user}.", ephemeral=True
        )
        return
    else:
        await interaction.response.send_message(
            "You cannot remove roles higher than or equal to your own.", ephemeral=True
        )


@bot.slash_command(
    name="ping-role",
    description="Pings a role in the server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
@application_checks.has_permissions(manage_roles=True)
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
    name="create-vc",
    description="Create a private voice channel in the server.",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
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
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            manage_channels=True,
            mute_members=True,
            move_members=True,
            deafen_members=True,
            view_channel=True,
        ),
    }
    if currency >= 10:
        currency_collection.update_one(query, {"$set": {"currency": currency - 10}})

        voice_channel = await guild.create_voice_channel(
            name=create_voice,
            user_limit=user_limit,
            overwrites=overwrites,
        )

        await interaction.response.send_message(
            f"{voice_channel.mention} voice channel has been created with a limit of {user_limit} users. Click on the name to join it.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "You do not have enough currency to create a voice channel.", ephemeral=True
        )


@bot.slash_command(
    name="find-in-vc",
    description="Find in which VC a user is in.",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
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
                    f"Found {user.name} in voice channel: {voice_channel.mention}",
                    ephemeral=True,
                )
                return
    await interaction.response.send_message(
        f"{user.name} is not currently in a voice channel.", ephemeral=True
    )


@bot.slash_command(
    name="vc-drag",
    description="Drag a person to a voice channel in server",
    guild_ids=[TESTING_GUILD_ID],
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
    name="request-vc-drag",
    description="Ask a mod for a drag request.",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
async def dragMe(
    interactor: discord.Interaction,
    user_name: discord.Member = discord.SlashOption(
        "drag", "Change VC for the selected user"
    ),
):

    if interactor.user.voice:
        if interactor.user.voice.channel == user_name.voice.channel:
            await interactor.response.send_message(
                "You're already in the same voice channel as that user!", ephemeral=True
            )
            return

        else:
            embed = discord.Embed(
                title=f"{interactor.user.name} wants to be dragged!",
                description=f"{interactor.user.name} has requested to join your voice channel ({user_name.voice.channel.name}).",
                color=0x00FFFF,
            )
            embed1 = discord.Embed(
                title=f"{interactor.user.name} has been dragged!",
                description=f"{user_name} has has accepted the request.",
                color=0x00FFFF,
            )
            view1 = View()
            embed2 = discord.Embed(
                title=f"{interactor.user.name} has been rejected to be dragged!",
                description=f"{user_name} has has rejected the request.",
                color=0x00FFFF,
            )
            accept_button = Button(label="Accept", style=discord.ButtonStyle.green)
            reject_button = Button(label="Reject", style=discord.ButtonStyle.red)

            async def accept_callback(interaction):
                if interaction.user.id != user_name.id:
                    await interaction.response.send_message(
                        "You can't accept this request!", ephemeral=True
                    )
                    return

                try:
                    await interactor.user.move_to(user_name.voice.channel)
                    await interaction.response.send_message(
                        f"Dragged {interactor.user.name} into your voice channel!",
                        ephemeral=True,
                    )
                    await interactor.edit_original_message(embed=embed1, view=view1)
                except discord.errors.HTTPException as e:
                    await interaction.response.send_message(
                        f"Failed to drag {interactor.user.name}: {e}", ephemeral=True
                    )

            async def reject_callback(interaction):
                if interaction.user.id != user_name.id:
                    await interaction.response.send_message(
                        "You can't reject this request!", ephemeral=True
                    )
                    return
                await interaction.response.send_message(
                    f"{user_name.name} has rejected the drag request."
                )
                await interactor.edit_original_message(embed=embed2, view=view1)

            accept_button.callback = accept_callback
            reject_button.callback = reject_callback

            view = View()
            view.add_item(accept_button)
            view.add_item(reject_button)

            await interactor.response.send_message(embed=embed, view=view)

    else:
        await interactor.response.send_message(
            "You're not in any voice channels.", ephemeral=True
        )


@bot.slash_command(
    name="help",
    description="Shows a list of all slash commands in the server",
    guild_ids=[TESTING_GUILD_ID],
)
@commands.has_guild_permissions(administrator=True)
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="My Commands")

    ban_desc = "To ban a user from the server."
    tempBan_desc = "To ban a user temporarily from the server."
    unban_desc = "To unban a user from the server."
    kick_desc = "To kick a user from the server."
    warn_desc = "To warn a user in the server."
    timeout_desc = "To timeout/mute a user in the server."
    nick_desc = "To change nickname of a user in the server."
    giveAdmin_desc = "To give Administrator Permissions to a user in the server."
    roles_desc = "To change roles of a user in the server."
    ping_desc = "To ping a role in the server."
    drag_desc = "To drag a user between VCs in the server."
    dragReq_desc = "To send a drag request for VCs in the server."
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
    queue_desc = "To show the music queue of the bot."

    embed.add_field(name="`/ban`", value=ban_desc, inline=False)
    embed.add_field(name="`/temp_ban`", value=tempBan_desc, inline=False)
    embed.add_field(name="`/unban`", value=unban_desc, inline=False)
    embed.add_field(name="`/kick`", value=kick_desc, inline=False)
    embed.add_field(name="`/warn`", value=warn_desc, inline=False)
    embed.add_field(name="`/timeout`", value=timeout_desc, inline=False)
    embed.add_field(name="`/nickname`", value=nick_desc, inline=False)
    embed.add_field(name="`/give_admin`", value=giveAdmin_desc, inline=False)
    embed.add_field(name="`/change_roles`", value=roles_desc, inline=False)
    embed.add_field(name="`/ping_role`", value=ping_desc, inline=False)
    embed.add_field(name="`/vc_drag`", value=drag_desc, inline=False)
    embed.add_field(name="`/request_vc_drag`", value=dragReq_desc, inline=False)
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
    embed.add_field(name="`c.queue`", value=queue_desc, inline=False)
    embed.add_field(
        name="`c.disconnect or c.dc or c.boot or c.stop or c.leave or c.end`",
        value=disconnect_desc,
        inline=False,
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

signal.signal(signal.SIGINT, signal_handler)


t1 = threading.Thread(target=background_unban_task, args=(bot,))
t1.start()

bot.run(config.get("BOT", "auth_token"))
t1.join()
