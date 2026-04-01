import os
import re
import sys

import discord
from discord import app_commands
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

VALID_TRIGGER_MODES = {"any", "all"}

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

    global_cfg = config.get("global", {})
    if not isinstance(global_cfg, dict):
        sys.exit("Error: config.yaml 'global' section must be a mapping.")
    if not isinstance(global_cfg.get("ignore_bots", False), bool):
        sys.exit("Error: 'global.ignore_bots' must be a boolean.")

    admin_users = global_cfg.get("admin_users")
    if admin_users is not None:
        if not isinstance(admin_users, list):
            sys.exit("Error: 'global.admin_users' must be a list.")
        for uid in admin_users:
            if not isinstance(uid, int):
                sys.exit(
                    f"Error: 'global.admin_users' entries must be integers, got {uid!r}."
                )

    admin_role = global_cfg.get("admin_role")
    if admin_role is not None and not isinstance(admin_role, (str, int)):
        sys.exit("Error: 'global.admin_role' must be a string or integer.")

    rules = config.get("rules")
    if not rules or not isinstance(rules, list):
        sys.exit("Error: config.yaml must contain a non-empty 'rules' list.")

    for idx, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            sys.exit(f"Error: rule #{idx} must be a mapping.")

        name = rule.get("name")
        if name is not None and not isinstance(name, str):
            sys.exit(f"Error: rule #{idx} 'name' must be a string.")

        trigger_mode = rule.get("trigger_mode", "any")
        if trigger_mode not in VALID_TRIGGER_MODES:
            sys.exit(
                f"Error: rule #{idx} 'trigger_mode' must be one of "
                f"{', '.join(sorted(VALID_TRIGGER_MODES))}, got {trigger_mode!r}."
            )

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
            if len(channels) == 0:
                sys.exit(
                    f"Error: rule #{idx} 'channels' must not be empty "
                    f"(omit the field to match all channels)."
                )
            for ch in channels:
                if not isinstance(ch, int):
                    sys.exit(
                        f"Error: rule #{idx} channel IDs must be integers, got {ch!r}."
                    )

        excluded_channels = rule.get("excluded_channels")
        if excluded_channels is not None:
            if not isinstance(excluded_channels, list):
                sys.exit(f"Error: rule #{idx} 'excluded_channels' must be a list.")
            for ch in excluded_channels:
                if not isinstance(ch, int):
                    sys.exit(
                        f"Error: rule #{idx} excluded channel IDs must be integers, got {ch!r}."
                    )

    return config


def save_config(config):
    """Write the current configuration back to the YAML file on disk."""
    config_path = os.getenv("CONFIG_PATH", "config.yaml")

    # Deep-copy and strip internal keys (e.g. _compiled) before saving
    clean = {}
    if "global" in config:
        clean["global"] = dict(config["global"])

    clean_rules = []
    for rule in config.get("rules", []):
        clean_rule = {}
        for key in ("name", "channels", "excluded_channels", "trigger_mode"):
            if key in rule:
                clean_rule[key] = rule[key]
        clean_triggers = []
        for t in rule.get("triggers", []):
            clean_triggers.append(
                {k: v for k, v in t.items() if not k.startswith("_")}
            )
        clean_rule["triggers"] = clean_triggers
        clean_rule["emojis"] = list(rule.get("emojis", []))
        clean_rules.append(clean_rule)
    clean["rules"] = clean_rules

    with open(config_path, "w", encoding="utf-8") as fh:
        yaml.dump(clean, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _find_rule(rules, identifier):
    """Find a rule by name or 1-based index. Returns (index, rule) or (None, None)."""
    # Try by name first
    for i, rule in enumerate(rules):
        if rule.get("name") == identifier:
            return i, rule
    # Try by 1-based index
    try:
        idx = int(identifier) - 1
        if 0 <= idx < len(rules):
            return idx, rules[idx]
    except (ValueError, TypeError):
        pass
    return None, None


def is_admin(interaction, global_cfg):
    """Check whether the interaction user is allowed to run config commands."""
    admin_users = global_cfg.get("admin_users")
    admin_role = global_cfg.get("admin_role")

    # If neither admin_users nor admin_role is configured, fall back to
    # Discord's manage_guild permission.
    if admin_users is None and admin_role is None:
        perms = interaction.user.guild_permissions
        return perms.manage_guild if hasattr(perms, "manage_guild") else False

    if admin_users and interaction.user.id in admin_users:
        return True

    if admin_role is not None:
        role_val = str(admin_role)
        if hasattr(interaction.user, "roles"):
            for r in interaction.user.roles:
                if str(r.id) == role_val or r.name == role_val:
                    return True

    return False


config = load_config()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    sys.exit("Error: DISCORD_TOKEN environment variable is not set.")

rules = config["rules"]
ignore_bots = config.get("global", {}).get("ignore_bots", False)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


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
    for idx, rule in enumerate(rules, 1):
        label = rule.get("name") or f"rule #{idx}"
        channels = rule.get("channels")
        channel_info = f"channels {channels}" if channels else "all channels"
        excluded = rule.get("excluded_channels")
        if excluded:
            channel_info += f" (excluding {excluded})"
        mode = rule.get("trigger_mode", "any")
        trigger_types = [t["type"] for t in rule["triggers"]]
        print(f"  Loaded {label!r}: {channel_info}, triggers ({mode}): {trigger_types}")
    await tree.sync()
    print("Slash commands synced.")


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if ignore_bots and message.author.bot:
        return

    for rule in rules:
        channels = rule.get("channels")
        if channels and message.channel.id not in channels:
            continue

        excluded_channels = rule.get("excluded_channels")
        if excluded_channels and message.channel.id in excluded_channels:
            continue

        triggers = rule["triggers"]
        trigger_mode = rule.get("trigger_mode", "any")

        # Skip rules that only contain thread_created triggers
        msg_triggers = [t for t in triggers if t["type"] != "thread_created"]
        if not msg_triggers:
            continue

        if trigger_mode == "all":
            matched = all(check_trigger(t, message) for t in msg_triggers)
        else:
            matched = any(check_trigger(t, message) for t in msg_triggers)

        if matched:
            await add_reactions(message, rule["emojis"])


@client.event
async def on_thread_create(thread):
    for rule in rules:
        channels = rule.get("channels")
        if channels and thread.parent_id not in channels:
            continue

        excluded_channels = rule.get("excluded_channels")
        if excluded_channels and thread.parent_id in excluded_channels:
            continue

        if not any(t["type"] == "thread_created" for t in rule["triggers"]):
            continue

        try:
            starter = thread.starter_message
            if starter is None:
                starter = await thread.fetch_message(thread.id)
        except discord.errors.DiscordException as exc:
            label = rule.get("name") or f"rule at index {rules.index(rule)}"
            print(f"Failed to fetch starter message in thread {thread.id} for {label!r}: {exc}")
            continue

        trigger_mode = rule.get("trigger_mode", "any")
        if trigger_mode == "all":
            non_thread_triggers = [t for t in rule["triggers"] if t["type"] != "thread_created"]
            if non_thread_triggers and not all(
                check_trigger(t, starter) for t in non_thread_triggers
            ):
                continue

        try:
            await add_reactions(starter, rule["emojis"])
        except discord.errors.DiscordException as exc:
            print(f"Failed to react in thread {thread.id}: {exc}")


# ---------------------------------------------------------------------------
# Slash commands – server configuration from Discord
# ---------------------------------------------------------------------------


def _admin_check(interaction):
    """Return an error message if the user is not an admin, else None."""
    global_cfg = config.get("global", {})
    if not is_admin(interaction, global_cfg):
        return "You do not have permission to use this command."
    return None


@tree.command(name="listconfig", description="Show the current reaction rules")
async def cmd_listconfig(interaction: discord.Interaction):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    global_cfg = config.get("global", {})
    lines = ["**Reactionary Configuration**\n"]
    if global_cfg:
        lines.append(f"**Global:** ignore_bots={global_cfg.get('ignore_bots', False)}")
        if global_cfg.get("admin_role"):
            lines.append(f"  admin_role: {global_cfg['admin_role']}")
        if global_cfg.get("admin_users"):
            lines.append(f"  admin_users: {global_cfg['admin_users']}")
        lines.append("")

    for idx, rule in enumerate(rules, 1):
        label = rule.get("name") or f"rule #{idx}"
        channels = rule.get("channels")
        ch_info = f"channels: {channels}" if channels else "all channels"
        excluded = rule.get("excluded_channels")
        if excluded:
            ch_info += f" (excl: {excluded})"
        mode = rule.get("trigger_mode", "any")
        triggers = ", ".join(
            t["type"] + (f"={t['value']}" if "value" in t else "")
            for t in rule["triggers"]
        )
        emojis = " ".join(rule["emojis"])
        lines.append(f"**{idx}. {label}**")
        lines.append(f"  {ch_info}")
        lines.append(f"  trigger_mode: {mode} | triggers: {triggers}")
        lines.append(f"  emojis: {emojis}")

    text = "\n".join(lines)
    # Discord messages have a 2000 char limit
    if len(text) > 1900:
        text = text[:1900] + "\n… (truncated)"
    await interaction.response.send_message(text, ephemeral=True)


@tree.command(name="addrule", description="Add a new reaction rule")
@app_commands.describe(
    name="Rule name",
    trigger_type="Trigger type",
    trigger_value="Trigger value (for contains/exact/regex/user/role)",
    emojis="Comma-separated emojis",
    channel="Channel ID to scope this rule to (optional)",
    trigger_mode="Trigger mode: any or all (default: any)",
)
@app_commands.choices(
    trigger_type=[
        app_commands.Choice(name=t, value=t)
        for t in sorted(VALID_TRIGGER_TYPES)
    ],
    trigger_mode=[
        app_commands.Choice(name="any", value="any"),
        app_commands.Choice(name="all", value="all"),
    ],
)
async def cmd_addrule(
    interaction: discord.Interaction,
    name: str,
    trigger_type: str,
    emojis: str,
    trigger_value: str = None,
    channel: str = None,
    trigger_mode: str = "any",
):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    if trigger_type in TRIGGERS_REQUIRING_VALUE and not trigger_value:
        await interaction.response.send_message(
            f"Trigger type `{trigger_type}` requires a `trigger_value`.",
            ephemeral=True,
        )
        return

    if trigger_type == "regex" and trigger_value:
        try:
            re.compile(trigger_value)
        except re.error as exc:
            await interaction.response.send_message(
                f"Invalid regex: {exc}", ephemeral=True
            )
            return

    trigger = {"type": trigger_type}
    if trigger_value:
        trigger["value"] = trigger_value
    if trigger_type == "regex" and trigger_value:
        trigger["_compiled"] = re.compile(trigger_value)

    emoji_list = [e.strip() for e in emojis.split(",") if e.strip()]
    if not emoji_list:
        await interaction.response.send_message(
            "At least one emoji is required.", ephemeral=True
        )
        return

    new_rule = {
        "name": name,
        "triggers": [trigger],
        "emojis": emoji_list,
    }
    if trigger_mode != "any":
        new_rule["trigger_mode"] = trigger_mode
    if channel:
        try:
            new_rule["channels"] = [int(channel)]
        except ValueError:
            await interaction.response.send_message(
                "Channel must be a valid integer ID.", ephemeral=True
            )
            return

    rules.append(new_rule)
    save_config(config)
    await interaction.response.send_message(
        f"✅ Rule **{name}** added (#{len(rules)}).", ephemeral=True
    )


@tree.command(name="removerule", description="Remove a rule by name or number")
@app_commands.describe(rule="Rule name or number (1-based)")
async def cmd_removerule(interaction: discord.Interaction, rule: str):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    idx, found = _find_rule(rules, rule)
    if found is None:
        await interaction.response.send_message(
            f"Rule `{rule}` not found.", ephemeral=True
        )
        return

    removed = rules.pop(idx)
    if not rules:
        # Must keep at least one rule for valid config; re-add and reject
        rules.insert(idx, removed)
        await interaction.response.send_message(
            "Cannot remove the last rule. At least one rule must exist.",
            ephemeral=True,
        )
        return

    save_config(config)
    label = removed.get("name") or f"rule #{idx + 1}"
    await interaction.response.send_message(
        f"✅ Removed rule **{label}**.", ephemeral=True
    )


@tree.command(name="addchannel", description="Add a channel to a rule")
@app_commands.describe(
    rule="Rule name or number",
    channel="Channel ID to add",
)
async def cmd_addchannel(interaction: discord.Interaction, rule: str, channel: str):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    idx, found = _find_rule(rules, rule)
    if found is None:
        await interaction.response.send_message(
            f"Rule `{rule}` not found.", ephemeral=True
        )
        return

    try:
        ch_id = int(channel)
    except ValueError:
        await interaction.response.send_message(
            "Channel must be a valid integer ID.", ephemeral=True
        )
        return

    if "channels" not in found:
        found["channels"] = []
    if ch_id in found["channels"]:
        await interaction.response.send_message(
            f"Channel `{ch_id}` is already in this rule.", ephemeral=True
        )
        return

    found["channels"].append(ch_id)
    save_config(config)
    label = found.get("name") or f"rule #{idx + 1}"
    await interaction.response.send_message(
        f"✅ Added channel `{ch_id}` to **{label}**.", ephemeral=True
    )


@tree.command(name="removechannel", description="Remove a channel from a rule")
@app_commands.describe(
    rule="Rule name or number",
    channel="Channel ID to remove",
)
async def cmd_removechannel(interaction: discord.Interaction, rule: str, channel: str):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    idx, found = _find_rule(rules, rule)
    if found is None:
        await interaction.response.send_message(
            f"Rule `{rule}` not found.", ephemeral=True
        )
        return

    try:
        ch_id = int(channel)
    except ValueError:
        await interaction.response.send_message(
            "Channel must be a valid integer ID.", ephemeral=True
        )
        return

    channels = found.get("channels")
    if not channels or ch_id not in channels:
        await interaction.response.send_message(
            f"Channel `{ch_id}` is not in this rule.", ephemeral=True
        )
        return

    channels.remove(ch_id)
    if not channels:
        del found["channels"]
    save_config(config)
    label = found.get("name") or f"rule #{idx + 1}"
    await interaction.response.send_message(
        f"✅ Removed channel `{ch_id}` from **{label}**.", ephemeral=True
    )


@tree.command(name="addemoji", description="Add an emoji to a rule")
@app_commands.describe(
    rule="Rule name or number",
    emoji="Emoji to add",
)
async def cmd_addemoji(interaction: discord.Interaction, rule: str, emoji: str):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    idx, found = _find_rule(rules, rule)
    if found is None:
        await interaction.response.send_message(
            f"Rule `{rule}` not found.", ephemeral=True
        )
        return

    if emoji in found["emojis"]:
        await interaction.response.send_message(
            f"Emoji {emoji} is already in this rule.", ephemeral=True
        )
        return

    found["emojis"].append(emoji)
    save_config(config)
    label = found.get("name") or f"rule #{idx + 1}"
    await interaction.response.send_message(
        f"✅ Added {emoji} to **{label}**.", ephemeral=True
    )


@tree.command(name="removeemoji", description="Remove an emoji from a rule")
@app_commands.describe(
    rule="Rule name or number",
    emoji="Emoji to remove",
)
async def cmd_removeemoji(interaction: discord.Interaction, rule: str, emoji: str):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    idx, found = _find_rule(rules, rule)
    if found is None:
        await interaction.response.send_message(
            f"Rule `{rule}` not found.", ephemeral=True
        )
        return

    if emoji not in found["emojis"]:
        await interaction.response.send_message(
            f"Emoji {emoji} is not in this rule.", ephemeral=True
        )
        return

    if len(found["emojis"]) <= 1:
        await interaction.response.send_message(
            "Cannot remove the last emoji from a rule.", ephemeral=True
        )
        return

    found["emojis"].remove(emoji)
    save_config(config)
    label = found.get("name") or f"rule #{idx + 1}"
    await interaction.response.send_message(
        f"✅ Removed {emoji} from **{label}**.", ephemeral=True
    )


@tree.command(name="addtrigger", description="Add a trigger to a rule")
@app_commands.describe(
    rule="Rule name or number",
    trigger_type="Trigger type to add",
    trigger_value="Value for the trigger (for contains/exact/regex/user/role)",
)
@app_commands.choices(
    trigger_type=[
        app_commands.Choice(name=t, value=t)
        for t in sorted(VALID_TRIGGER_TYPES)
    ]
)
async def cmd_addtrigger(
    interaction: discord.Interaction,
    rule: str,
    trigger_type: str,
    trigger_value: str = None,
):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    idx, found = _find_rule(rules, rule)
    if found is None:
        await interaction.response.send_message(
            f"Rule `{rule}` not found.", ephemeral=True
        )
        return

    if trigger_type in TRIGGERS_REQUIRING_VALUE and not trigger_value:
        await interaction.response.send_message(
            f"Trigger type `{trigger_type}` requires a `trigger_value`.",
            ephemeral=True,
        )
        return

    if trigger_type == "regex" and trigger_value:
        try:
            re.compile(trigger_value)
        except re.error as exc:
            await interaction.response.send_message(
                f"Invalid regex: {exc}", ephemeral=True
            )
            return

    trigger = {"type": trigger_type}
    if trigger_value:
        trigger["value"] = trigger_value
    if trigger_type == "regex" and trigger_value:
        trigger["_compiled"] = re.compile(trigger_value)

    found["triggers"].append(trigger)
    save_config(config)
    label = found.get("name") or f"rule #{idx + 1}"
    await interaction.response.send_message(
        f"✅ Added trigger `{trigger_type}` to **{label}**.", ephemeral=True
    )


@tree.command(name="removetrigger", description="Remove a trigger from a rule")
@app_commands.describe(
    rule="Rule name or number",
    trigger_type="Trigger type to remove",
    trigger_value="Value to match (for contains/exact/regex/user/role)",
)
@app_commands.choices(
    trigger_type=[
        app_commands.Choice(name=t, value=t)
        for t in sorted(VALID_TRIGGER_TYPES)
    ]
)
async def cmd_removetrigger(
    interaction: discord.Interaction,
    rule: str,
    trigger_type: str,
    trigger_value: str = None,
):
    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    idx, found = _find_rule(rules, rule)
    if found is None:
        await interaction.response.send_message(
            f"Rule `{rule}` not found.", ephemeral=True
        )
        return

    # Find matching trigger
    match_idx = None
    for i, t in enumerate(found["triggers"]):
        if t["type"] == trigger_type:
            if trigger_type in TRIGGERS_REQUIRING_VALUE:
                if t.get("value") == trigger_value:
                    match_idx = i
                    break
            else:
                match_idx = i
                break

    if match_idx is None:
        await interaction.response.send_message(
            f"Trigger `{trigger_type}` not found in this rule.", ephemeral=True
        )
        return

    if len(found["triggers"]) <= 1:
        await interaction.response.send_message(
            "Cannot remove the last trigger from a rule.", ephemeral=True
        )
        return

    found["triggers"].pop(match_idx)
    save_config(config)
    label = found.get("name") or f"rule #{idx + 1}"
    await interaction.response.send_message(
        f"✅ Removed trigger `{trigger_type}` from **{label}**.", ephemeral=True
    )


@tree.command(name="togglebots", description="Toggle the ignore_bots global setting")
async def cmd_togglebots(interaction: discord.Interaction):
    global ignore_bots

    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    if "global" not in config:
        config["global"] = {}
    current = config["global"].get("ignore_bots", False)
    config["global"]["ignore_bots"] = not current
    ignore_bots = not current
    save_config(config)
    state = "enabled" if ignore_bots else "disabled"
    await interaction.response.send_message(
        f"✅ `ignore_bots` is now **{state}**.", ephemeral=True
    )


@tree.command(name="reloadconfig", description="Reload configuration from disk")
async def cmd_reloadconfig(interaction: discord.Interaction):
    global config, rules, ignore_bots

    err = _admin_check(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return

    try:
        new_config = load_config()
    except SystemExit as exc:
        await interaction.response.send_message(
            f"❌ Config reload failed: {exc}", ephemeral=True
        )
        return

    config = new_config
    rules = config["rules"]
    ignore_bots = config.get("global", {}).get("ignore_bots", False)
    await interaction.response.send_message(
        f"✅ Configuration reloaded. {len(rules)} rule(s) loaded.", ephemeral=True
    )


client.run(TOKEN)
