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
intents.reactions = True
intents.typing = True
intents.messages = True

bot = discord.Client(intents=intents)

member_voice_times = {}

TARGETING_VOICE_CHANNELS = [
    748394748099821652,
    1098631003381170217,
    1222575664364916768,
    1222575796686950480
]

AUDIT_LOG_CHANNEL = 1222575735332409495

MESSAGE_LOG_CHANNEL = 1222575735332409495


# class HandleLog(commands.Cog):
#     def __init__(self, client):
#         self.client = client

if __name__ == "__main__":

    @bot.event
    async def on_ready():
        print(f"We have logged in as {bot.user}")

    def get_current_unix_time():
        return int(time.time())

    def get_time_difference(timestamp1, timestamp2):
        diff = abs(timestamp1 - timestamp2)

        if diff < 60:
            return f"{diff} seconds"
        elif diff < 3600:
            minutes = diff // 60
            return f"{minutes} minutes"
        elif diff < 86400:
            hours = diff // 3600
            return f"{hours} hours"
        else:
            days = diff // 86400
            return f"{days} days"

    current_time = get_current_unix_time()

    async def log_message(message):
        # if MESSAGE_LOG_CHANNEL:
        #     message_log_channel = bot.get_channel(MESSAGE_LOG_CHANNEL)
        #     if message_log_channel:
        #         await message_log_channel.send(message)

        if AUDIT_LOG_CHANNEL:
            audit_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
            if audit_channel:
                await audit_channel.send(message)

    async def log_event(event_type, user, content):
        # log_channel = bot.get_channel(MESSAGE_LOG_CHANNEL)
        # if log_channel:
        #     embed = discord.Embed(title=event_type, description=content)
        #     embed.set_author(
        #         name=user.name, icon_url=user.avatar.url if user.avatar else ""
        #     )
        #     embed.set_footer(text=f"User ID: {user.id}")
        #     await log_channel.send(embed=embed)

        log_channel = bot.get_channel(AUDIT_LOG_CHANNEL)
        if log_channel:
            embed = discord.Embed(title=event_type, description=content)
            embed.set_author(
                name=user.name, icon_url=user.avatar.url if user.avatar else ""
            )
            embed.set_footer(text=f"User ID: {user.id}")
            await log_channel.send(embed=embed)

    @bot.event
    async def on_message(message):

        if message.author == bot.user:
            return
        print(message.author, message.channel.name, message.content, message.embeds)
        
        if message.author.id != bot.application_id:
            await log_event(
                "Message sent", message.author, message.content
            )

    @bot.event
    async def on_message_delete(message):
        if message.author.id != bot.application_id:
            await log_event(
                "Message Deleted", message.author, message.content
            )

    @bot.event
    async def on_message_edit(before, after):
        if (
            before.author.id != bot.application_id
            and after.author.id != bot.application_id
        ):
            await log_event(
                "Message Edited",
                before.author,
                f"**Before:** {before.content}\n**After:** {after.content}",
            )

    @bot.event
    async def on_voice_state_update(member, before, after):

        if member.id != bot.application_id:

            target_voice_channel_ids = [TARGETING_VOICE_CHANNELS]

            if (
                before.channel is None
                and after.channel is not None
                and after.channel.id in target_voice_channel_ids
            ) or (
                before.channel is not None
                and before.channel.id in target_voice_channel_ids
                and after.channel is None
            ):

                channel_id = (
                    after.channel.id if after.channel else before.channel.id
                )
                channel_name = (
                    after.channel.name if after.channel else before.channel.name
                )

                if before.channel is None:
                    member_voice_times[(member, channel_id)] = datetime.now(
                        timezone.utc
                    )
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

    async def on_member_update(before, after):

        if (
            before.author.id != bot.application_id
            and after.author.id != bot.application_id
        ):

            if before.roles != after.roles:
                added_roles = [
                    role for role in after.roles if role not in before.roles
                ]
                removed_roles = [
                    role for role in before.roles if role not in after.roles
                ]
                log_message = f"Member Role Update: {after.name} (ID: {after.id})\n"
                if added_roles:
                    log_message += f"Added Roles: {', '.join(role.name for role in added_roles)}\n"
                if removed_roles:
                    log_message += f"Removed Roles: {', '.join(role.name for role in removed_roles)}\n"
                await log_event(
                    "Member Updated", before, f"{log_message}"
                )

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

    bot.run(CONFIG["auth_token"])
