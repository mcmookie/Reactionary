import os
import re
import sys

import discord
import yaml
from dotenv import load_dotenv

load_dotenv()

VALID_TRIGGER_TYPES = {
    "all",
    "embed",
    "attachment",
    "contains",
    "exact",
    "regex",
    "has_link",
    "has_sticker",
    "reply",
    "mention_bot",
    "mention_any",
    "user",
    "role",
    "thread_created",
}

TRIGGERS_REQUIRING_VALUE = {"contains", "exact", "regex", "user", "role"}

LINK_PATTERN = re.compile(r"https?://\S+")


def load_config():
    """Load and validate the YAML configuration file."""
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    if not os.path.exists(config_path):
        sys.exit(f"Error: config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    if not isinstance(config, dict):
        sys.exit("Error: config.yaml must be a YAML mapping at the top level.")

    rules = config.get("rules")
    if not rules or not isinstance(rules, list):
        sys.exit("Error: config.yaml must contain a non-empty 'rules' list.")

    for idx, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            sys.exit(f"Error: rule #{idx} must be a mapping.")

        triggers = rule.get("triggers")
        if not triggers or not isinstance(triggers, list):
            sys.exit(f"Error: rule #{idx} must have a non-empty 'triggers' list.")

        for trigger in triggers:
            ttype = trigger.get("type")
            if ttype not in VALID_TRIGGER_TYPES:
                sys.exit(
                    f"Error: rule #{idx} has invalid trigger type {ttype!r}. "
                    f"Valid types: {', '.join(sorted(VALID_TRIGGER_TYPES))}"
                )
            if ttype in TRIGGERS_REQUIRING_VALUE and "value" not in trigger:
                sys.exit(
                    f"Error: rule #{idx} trigger '{ttype}' requires a 'value' field."
                )
            if ttype == "regex":
                try:
                    trigger["_compiled"] = re.compile(trigger["value"])
                except re.error as exc:
                    sys.exit(
                        f"Error: rule #{idx} has invalid regex {trigger['value']!r}: {exc}"
                    )

        emojis = rule.get("emojis")
        if not emojis or not isinstance(emojis, list):
            sys.exit(f"Error: rule #{idx} must have a non-empty 'emojis' list.")

        channels = rule.get("channels")
        if channels is not None:
            if not isinstance(channels, list):
                sys.exit(f"Error: rule #{idx} 'channels' must be a list.")
            for ch in channels:
                if not isinstance(ch, int):
                    sys.exit(
                        f"Error: rule #{idx} channel IDs must be integers, got {ch!r}."
                    )

    return config


config = load_config()

TOKEN = os.getenv("DISCORD_TOKEN") or config.get("discord_token")
if not TOKEN:
    sys.exit(
        "Error: DISCORD_TOKEN is not set. "
        "Provide it via the DISCORD_TOKEN environment variable or "
        "the 'discord_token' field in config.yaml."
    )

rules = config["rules"]

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)


def check_trigger(trigger, message):
    """Return True if *message* satisfies the given *trigger*."""
    ttype = trigger["type"]

    if ttype == "all":
        return True
    if ttype == "embed":
        return bool(message.embeds)
    if ttype == "attachment":
        return bool(message.attachments)
    if ttype == "contains":
        return trigger["value"].lower() in message.content.lower()
    if ttype == "exact":
        return message.content == trigger["value"]
    if ttype == "regex":
        compiled = trigger.get("_compiled") or re.compile(trigger["value"])
        return bool(compiled.search(message.content))
    if ttype == "has_link":
        return bool(LINK_PATTERN.search(message.content))
    if ttype == "has_sticker":
        return bool(message.stickers)
    if ttype == "reply":
        return message.reference is not None
    if ttype == "mention_bot":
        return client.user in message.mentions
    if ttype == "mention_any":
        return bool(message.mentions)
    if ttype == "user":
        return str(message.author.id) == str(trigger["value"])
    if ttype == "role":
        if hasattr(message.author, "roles"):
            role_value = str(trigger["value"])
            return any(
                str(r.id) == role_value or r.name == role_value
                for r in message.author.roles
            )
        return False

    return False


async def add_reactions(target, emojis):
    """Add a list of emoji reactions to *target* (a message)."""
    for emoji in emojis:
        try:
            await target.add_reaction(emoji)
        except discord.errors.DiscordException as exc:
            print(f"Failed to add reaction {emoji!r} to message {target.id}: {exc}")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    for rule in rules:
        channels = rule.get("channels")
        if channels and message.channel.id not in channels:
            continue

        triggers = rule["triggers"]

        # Skip rules that only contain thread_created triggers
        msg_triggers = [t for t in triggers if t["type"] != "thread_created"]
        if not msg_triggers:
            continue

        if any(check_trigger(t, message) for t in msg_triggers):
            await add_reactions(message, rule["emojis"])


@client.event
async def on_thread_create(thread):
    for rule in rules:
        channels = rule.get("channels")
        if channels and thread.parent_id not in channels:
            continue

        if not any(t["type"] == "thread_created" for t in rule["triggers"]):
            continue

        try:
            starter = thread.starter_message
            if starter is None:
                starter = await thread.fetch_message(thread.id)
            await add_reactions(starter, rule["emojis"])
        except discord.errors.DiscordException as exc:
            print(f"Failed to react in thread {thread.id}: {exc}")


client.run(TOKEN)
