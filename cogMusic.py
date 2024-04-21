import nextcord as discord
import yt_dlp as youtube_dl
import asyncio
import os
from nextcord.ext import commands
from collections import deque
from pytube import Search

from settings import CONFIG

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


@bot.event
async def on_ready():
    print(f"{bot.user} has logged in")


def delete_songs():
    for file in os.listdir():
        if file.endswith(".mp3"):
            os.remove(file)


def get_youtube_url(search_term, result_index=0):
    results = Search(search_term).results
    if results:
        return results[result_index].watch_url
    else:
        return None


async def play_queue(ctx):
    global music_queue
    global disconnect_now
    while music_queue:

        url = music_queue.popleft()

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                song_info = ydl.extract_info(url, download=True)
            filename = song_info["title"] + " [" + song_info["id"] + "].mp3"
            source = await discord.FFmpegOpusAudio.from_probe(
                "next_url", **ffmpeg_options
            )

            ctx.voice_client.play(discord.FFmpegPCMAudio(filename, **ffmpeg_options))
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


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


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

        try:
            await play_queue(ctx)
        except Exception as e:
            print(f"Error during playback: {e}")
            await ctx.send(
                "An error occurred while playing music. Please try again later."
            )


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

    delete_songs()

    await ctx.send("Player disconnected.")


@bot.command(name="skip")
async def skip(ctx):
    global disconnect_now

    ctx.voice_client.stop()

    disconnect_now = True
    await asyncio.sleep(2)

    ctx.voice_client.resume()

    await ctx.send("Song skipped.")


# def runbot():

bot.run(CONFIG["auth_token"])
