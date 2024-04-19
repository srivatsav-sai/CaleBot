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

# bot = discord.Client(intents=intents)
bot = commands.Bot(command_prefix="c.", intents=intents)

cluster = MongoClient("mongodb://localhost:27017/")
db = cluster["bottesting1"]
collection = db["discordserver"]


# class HandleLevel(commands.Cog):
#     def __init__(self, client):
#         self.client = client

    # logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":

    @bot.event
    async def on_ready():
        print(f"We have logged in as {bot.user}")

    @bot.event
    async def check_level_up(channel, message, collection):
        query = {"_id": message.author.id}
        user = collection.find_one(query)

        if not user:
            post = {"_id": message.author.id, "score": 0, "currency": 0, "level": 0}
            collection.insert_one(post)
            return

        score = user.get("score", 0)
        if score % 100 == 0:
            level = score // 100
            log_message = f"{message.author.mention}"
            await channel.send(
                f"Congratulations, {log_message}! You have reached level {level}!"
            )
        if score % 10 == 0:
            currency = score // 10
            log_message = f"{message.author.mention}"
            await channel.send(
                f"Congratulations, {log_message}! You now have {currency} unit{'s' if  currency > 1 else ''} currency!"
            )

    @bot.event
    async def on_message(message):

        # if message.author == bot.user:
        #     return
        # print(message.author, message.channel.name, message.content, message.embeds)

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
                    score = result["score"]
                score = score + 1
                level = score // 100
                currency = score // 10
                collection.update_one(
                    {"_id": message.author.id},
                    {
                        "$set": {
                            "score": score,
                            "currency": currency,
                            "level": level,
                        }
                    },
                )
        await check_level_up(message.channel, message, collection)

    @bot.command(name="get_currency")
    async def on_message(message):
        print("command noticed")
        if message.author in message.channel:
            await check_level_up()

    bot.run(CONFIG["auth_token"])
