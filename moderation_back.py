import nextcord as discord
import time
import asyncio
import re

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
link_regex = r"(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|www\.[a-zA-Z0-9]+\.[^\s]{2,})"
def strip_url(url):
    # Remove the protocol (e.g., "https://", "http://", "ftp://")
    url = re.sub(r'^(?:https?|ftp)://', '', url)
    
    # Remove any path or query parameters
    url = re.sub(r'/.*$', '', url)
    
    return url

COMMAND_PREFIX = "c."

client = discord.Client(intents=intents)

# Customizable anti-spam, anti-nuke and anti-link measures
# ignored_roles = ['Verified', 'Bot']
message_cooldown = 6  # Seconds between allowed messages per user
user_cooldown = 6  # Seconds between allowed message bursts per user
max_messages_per_burst = 3  # Limit on consecutive messages within cooldown
audit_log_channel = None  # Channel ID for logging anti-nuke events
allowed_link_domains = ["youtube.com"]  # Whitelisted domains for links
allowed_link_channels = []  # Whitelisted channels for links

message_cooldowns = {}  # Track per-user message cooldowns
user_cooldowns = {}  # Track per-user cooldown for bursts

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')

# async def fetch_msg_contents(message):
#     print(message.content)
#     print(message.embeds)
#     if message.content.startswith(COMMAND_PREFIX):
#         command = message.content.split()[0][1:]
#         args = message.content.split()[1:]

#         if command == 'echo':
#             if args:
#                 await message.channel.send(f" ".join(args))
#             else:
#                 await message.channel.send("You didn't provide anything to echo!")
#         else:
#             await message.channel.send(f"Unknown command: {command}")
#     else:
#         ()

async def log_message(message):
    if audit_log_channel:
        audit_channel = client.get_channel(audit_log_channel)
        if audit_channel:
            await audit_channel.send(message)

@client.event
async def on_message(message):
    if message.author == client.user:
        return  # Ignore messages from the bot itself
    # await fetch_msg_contents(message)
    print(message.author, message.channel.name, message.content, message.embeds)
    # Check for message containing links (excluding whitelisted channels)
    
    matches = re.findall(link_regex, message.content, re.IGNORECASE)

    for match in matches:
        print(match)
        print(strip_url(match))
        print(strip_url(match) not in allowed_link_domains)
        if strip_url(match) not in allowed_link_domains:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, links are not allowed in this channel.")
    # if any(re.match(link_regex, link.url) and link.url not in allowed_link_domains for link in message.embeds if link.url) and message.channel.id not in allowed_link_channels:
        # Optional logging (consider using a separate function)
        # print(f"Author: {message.author} ({message.author.id})")
        # print(f"Channel: {message.channel.name} ({message.channel.id})")
        # if message.embeds:
        #         print("Embedded Objects:")
        #         for embed in message.embeds:
        #             print(f"- Title: {embed.title}")
        #             print(f"- Description: {embed.description}")
        #             if embed.url:
        #                 print(f"- URL: {embed.url}")
        # Take action against the message (e.g., delete, warn)
        # await message.channel.send(f"{message.author.mention}, links are not allowed in this channel.")
        # print(f"Deleted message with unauthorized link: {message.content} (User: {message.author}, Channel: {message.channel.name})")                


    author = message.author
    current_time = time.time()

    # Check for per-user message cooldown violation
    if author in message_cooldowns:
        if current_time - message_cooldowns[author] < message_cooldown:
            await message.delete()
            await message.channel.send(f"{author.mention}, please wait {message_cooldown - (current_time - message_cooldowns[author]):.2f} seconds before sending another message.")
            return
    else:
        message_cooldowns[author] = current_time

    # Check for per-user cooldown violation for message bursts
    if author in user_cooldowns:
        if current_time - user_cooldowns[author][0] < user_cooldown:
            if len(user_cooldowns[author]) >= max_messages_per_burst:
                await message.delete()
                await message.channel.send(f"{author.mention}, you've sent too many messages in a short time. Please wait {user_cooldown - (current_time - user_cooldowns[author][0]):.2f} seconds before sending more.")
                user_cooldowns[author].pop(0)  # Remove the oldest message from the burst
                user_cooldowns[author].append(current_time)  # Add the current message to the burst
            else:
                user_cooldowns[author].append(current_time)
        else:
            user_cooldowns[author] = [current_time]  # Reset the burst cooldown for the user
    else:
        user_cooldowns[author] = [current_time]

    



client.run('MTIyMTczNzIzMDI4NTE0NDA5NQ.GXVsMK.DKcf411v8ewYSxLQzRv5sSoaOWWpdPTJjnlS1I')
