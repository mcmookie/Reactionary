import os
import sys
import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
_channel_id_raw = os.getenv("CHANNEL_ID")
REACTION_EMOJI = os.getenv("REACTION_EMOJI", "👍")

if not TOKEN:
    sys.exit("Error: DISCORD_TOKEN environment variable is not set.")
if not _channel_id_raw:
    sys.exit("Error: CHANNEL_ID environment variable is not set.")
try:
    CHANNEL_ID = int(_channel_id_raw)
except ValueError:
    sys.exit(f"Error: CHANNEL_ID must be a numeric value, got: {_channel_id_raw!r}")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.channel.id != CHANNEL_ID:
        return
    if message.author == client.user:
        return
    if message.embeds:
        try:
            await message.add_reaction(REACTION_EMOJI)
        except discord.errors.DiscordException as e:
            print(f"Failed to add reaction to message {message.id}: {e}")


client.run(TOKEN)
