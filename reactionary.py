import os
import sys
import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    sys.exit("Error: DISCORD_TOKEN environment variable is not set.")

DEFAULT_EMOJI = "👍"

channels_raw = os.getenv("CHANNELS", "")
CHANNEL_REACTIONS = {}
for entry in channels_raw.split("|"):
    entry = entry.strip()
    if not entry:
        continue
    if ":" not in entry:
        sys.exit(f"Error: invalid CHANNELS entry (missing ':'): {entry!r}")
    channel_part, _, emojis_part = entry.partition(":")
    channel_part = channel_part.strip()
    try:
        channel_id = int(channel_part)
    except ValueError:
        sys.exit(f"Error: channel ID must be numeric, got: {channel_part!r}")
    emojis = [e.strip() for e in emojis_part.split(",") if e.strip()] or [DEFAULT_EMOJI]
    CHANNEL_REACTIONS[channel_id] = emojis

if not CHANNEL_REACTIONS:
    sys.exit("Error: CHANNELS environment variable is not set or empty.")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.channel.id not in CHANNEL_REACTIONS:
        return
    if message.author == client.user:
        return
    if message.embeds:
        for emoji in CHANNEL_REACTIONS[message.channel.id]:
            try:
                await message.add_reaction(emoji)
            except discord.errors.DiscordException as e:
                print(f"Failed to add reaction {emoji!r} to message {message.id}: {e}")


client.run(TOKEN)
