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

message_cooldowns = {}
user_cooldowns = {}

LINK_REGEX = r"(https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?:\/\/(?:www\.|(?!www))[a-zA-Z0-9]+\.[^\s]{2,}|www\.[a-zA-Z0-9]+\.[^\s]{2,})"
MESSAGE_COOLDOWN = 10
USER_COOLDOWN = 60
MAX_MESSAGES_PER_BURST = 5
AUDIT_LOG_CHANNEL = 1222575735332409495
ALLOWED_LINK_DOMAINS = ["youtube.com"]
ALLOWED_LINK_CHANNELS = []


# class HandleMod(commands.Cog):
#     def __init__(self, client):
#         self.client = client

if __name__ == "__main__":

    def strip_url(url):
        url = re.sub(r"^(?:https?|ftp)://", "", url)
        url = re.sub(r"/.*$", "", url)
        return url

    @bot.event
    async def on_ready():
        print(f"We have logged in as {bot.user}")

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
        print(message.author, message.channel.name, message.content, message.embeds)

        # anti-link system
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
                        reason=f"{author.mention}, please wait {MESSAGE_COOLDOWN - (current_time - message_cooldowns[author]):.2f}seconds before sending another message.",
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

    @bot.slash_command(
        description="My first slash command", guild_ids=[TESTING_GUILD_ID]
    )
    async def hello(interaction: discord.Interaction):
        await interaction.send("Hello!")

    @bot.slash_command(
        name="kick",
        description="kick a person from server",
        guild_ids=[TESTING_GUILD_ID],
    )
    @commands.has_permissions(administrator=True)
    @application_checks.has_permissions(manage_messages=True)
    async def memberKick(
        
        interaction: discord.Interaction,
        user: discord.User = discord.SlashOption("kick", "kick a user from server"),
        reason: str = discord.SlashOption(
            "reason", "provide a reason to kick the selected user"
        ),
    ):
        await interaction.guild.kick(user, reason=reason)
        await interaction.send(f"{user} has been kicked", ephemeral=True)

    @bot.slash_command(
        name="ban",
        description="ban a person from server",
        guild_ids=[TESTING_GUILD_ID],
    )
    @commands.has_permissions(administrator=True)
    @application_checks.has_permissions(manage_messages=True)
    async def memberBan(
        
        interaction: discord.Interaction,
        user: discord.User = discord.SlashOption("ban", "ban a user from server"),
        delete_message_days: discord.User = discord.SlashOption(
            "delete_message_days", "delete this user's previous messages upto"
        ),
        reason: str = discord.SlashOption(
            "reason", "provide a reason to ban the selected user"
        ),
    ):
        await interaction.guild.ban(
            user, delete_message_days=delete_message_days, reason=reason
        )
        await interaction.send(f"{user} has been banned", ephemeral=True)

    @bot.slash_command(
        name="unban",
        description="unban a person from server",
        guild_ids=[TESTING_GUILD_ID],
    )
    @commands.has_permissions(administrator=True)
    @application_checks.has_permissions(manage_messages=True)
    async def memberUnban(
        
        interaction: discord.Interaction,
        user: str = discord.SlashOption("unban", "unban a user from server"),
        reason: str = discord.SlashOption(
            "reason", "provide a reason to unban the selected user"
        ),
    ):
        await interaction.guild.unban(discord.User(id=user), reason=reason)
        await interaction.send(f"{user} has been unbanned", ephemeral=True)

    @bot.slash_command(
        name="timeout",
        description="timeout a person in server",
        guild_ids=[TESTING_GUILD_ID],
    )
    @commands.has_permissions(administrator=True)
    @application_checks.has_permissions(manage_messages=True)
    async def memberMute(
        
        interaction: discord.Interaction,
        timeout: int,
        user: discord.Member = discord.SlashOption(
            "user", "timeout a user in minutes in server"
        ),
        reason: str = discord.SlashOption(
            "reason", "provide a reason to timeout the selected user"
        ),
    ):
        delta = timedelta(minutes=timeout)
        await user.timeout(timeout=delta, reason=reason)
        await interaction.send(f"{user} has been muted", ephemeral=True)

    @bot.slash_command(
        name="nickname",
        description="nickname a person in server",
        guild_ids=[TESTING_GUILD_ID],
    )
    @commands.has_permissions(administrator=True)
    @application_checks.has_permissions(manage_nicknames=True)
    async def changeNick(
        
        interaction: discord.Interaction,
        user: discord.Member = discord.SlashOption(
            "user", "select a user to change nickname in server"
        ),
        nickname: str = discord.SlashOption(
            "nickname", "enter a new nickname for the selected user"
        ),
    ):
        await user.edit(nick=nickname)
        await interaction.send(
            f"Nickname of {user} has been changed.", ephemeral=True
        )

    @bot.slash_command(
        name="roles",
        description="nickname a person in server",
        guild_ids=[TESTING_GUILD_ID],
    )
    @commands.has_permissions(administrator=True)
    @application_checks.has_permissions(manage_roles=True)
    async def manageRoles(
        
        interaction: discord.Interaction,
        user: discord.Member = discord.SlashOption(
            "user", "select a user to  their manage roles in server"
        ),
        manage_roles: str = discord.SlashOption(
            "roles", "manage roles for the selected user"
        ),
    ):
        await user.edit(roles=manage_roles)
        await interaction.send(f"Roles have been updated to {user}", ephemeral=True)

    @bot.slash_command(
        name="drag",
        description="drag a person in a vc in server",
        guild_ids=[TESTING_GUILD_ID],
    )
    @commands.has_permissions(administrator=True)
    @application_checks.has_permissions(move_members=True)
    async def voiceDrag(
        
        interaction: discord.Interaction,
        user: discord.Member = discord.SlashOption(
            "user", "select a user to  their manage roles in server"
        ),
        change_vc: str = discord.SlashOption(
            "drag", "change VC for the selected user"
        ),
    ):
        await user.move_to(voice_channel=change_vc)
        await interaction.send(
            f"{user} has been dragged to {change_vc}", ephemeral=True
        )

    bot.run(CONFIG["auth_token"])
