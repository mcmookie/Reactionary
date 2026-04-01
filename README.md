# Reactionary

A flexible Discord bot that automatically reacts to messages based on configurable rules and triggers.

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application.
2. Under **Bot**, create a bot user and copy the token.
3. Enable the **Message Content Intent** and **Server Members Intent** under **Privileged Gateway Intents**.
4. Invite the bot to your server with the `bot` scope and the `Add Reactions` + `Read Messages` permissions.

### 2. Configure the Bot

Copy the example files and fill in your values:

```bash
cp .env.example .env          # add your bot token here
cp config.yaml.example config.yaml  # define your reaction rules here
```

The bot token is a secret and must be set in `.env` (as `DISCORD_TOKEN`). Never put secrets in `config.yaml`.

To get a channel, user, or role ID, enable **Developer Mode** in Discord settings, then right-click the item and select **Copy ID**.

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Bot

```bash
python reactionary.py
```

By default the bot looks for `config.yaml` in the current directory. Set the `CONFIG_PATH` environment variable to use a different path.

## Configuration

All reaction behaviour is defined in `config.yaml` as a list of **rules**. Each rule specifies which channels to watch, what triggers to match, and which emojis to add.

```yaml
rules:
  - channels:          # list of channel IDs (omit to match all channels)
      - 111111111111
    triggers:          # at least one trigger must match
      - type: embed
    emojis:            # reactions to add when a trigger matches
      - "👍"
      - "🎉"
```

### Rule Fields

| Field | Required | Description |
|-------|----------|-------------|
| `triggers` | ✅ | List of trigger conditions (see below) |
| `emojis` | ✅ | List of emoji reactions to add |
| `channels` | — | Channel IDs to watch; omit to apply to all channels |
| `excluded_channels` | — | Channel IDs to skip; useful with global rules |
| `trigger_mode` | — | `"any"` (default) or `"all"` — see below |
| `name` | — | Optional label shown in startup logs for easier debugging |

### Trigger Types

| Trigger | Description | `value` field |
|---------|-------------|---------------|
| `all` | Matches every message | — |
| `embed` | Message contains an embed | — |
| `attachment` | Message has a file attachment | — |
| `contains` | Message text contains the value (case-insensitive) | required |
| `exact` | Message text matches the value exactly | required |
| `regex` | Message text matches a regular expression | required |
| `has_link` | Message contains an `http://` or `https://` URL | — |
| `has_sticker` | Message includes a sticker | — |
| `reply` | Message is a reply to another message | — |
| `mention_bot` | Message mentions the bot | — |
| `mention_any` | Message mentions any user | — |
| `user` | Message is from a specific user (by user ID) | required |
| `role` | Message is from a user with a specific role (by role ID or name) | required |
| `thread_created` | A new thread is created (reacts to the starter message) | — |

### `trigger_mode`

Controls how multiple triggers within a rule are combined:

- **`"any"`** (default) — fires when **any** trigger matches (logical OR)
- **`"all"`** — fires only when **every** trigger matches (logical AND)

```yaml
rules:
  # OR: react to embeds OR attachments
  - channels:
      - 111111111111
    trigger_mode: "any"
    triggers:
      - type: embed
      - type: attachment
    emojis:
      - "📎"

  # AND: react only when a link is posted by a Moderator
  - channels:
      - 222222222222
    trigger_mode: "all"
    triggers:
      - type: has_link
      - type: role
        value: "Moderator"
    emojis:
      - "🔗"
```

When `trigger_mode: "all"` is used with a `thread_created` trigger alongside other triggers, all the non-`thread_created` triggers are evaluated against the thread's starter message. The rule fires only if every trigger matches.

### `excluded_channels`

Excludes specific channels from an otherwise global rule (one with no `channels` list):

```yaml
rules:
  # React to all messages server-wide, except in the spam channel
  - excluded_channels:
      - 999999999999
    triggers:
      - type: all
    emojis:
      - "👍"
```

### Global Settings

An optional `global` section at the top of `config.yaml` sets server-wide defaults:

```yaml
global:
  ignore_bots: true   # ignore messages from other bots (default: false)
```

| Field | Default | Description |
|-------|---------|-------------|
| `ignore_bots` | `false` | When `true`, messages from any bot (other than the bot itself) are ignored |
| `admin_role` | — | Role name or ID required to use slash commands. If neither `admin_role` nor `admin_users` is set, users with the **Manage Server** permission can use commands |
| `admin_users` | — | List of user IDs allowed to use slash commands |

### Slash Commands

The bot registers Discord slash commands that let admins manage the configuration live from Discord. Changes are saved to `config.yaml` automatically.

| Command | Description |
|---------|-------------|
| `/listconfig` | Show all current rules and global settings |
| `/addrule` | Add a new reaction rule |
| `/removerule` | Remove a rule by name or number |
| `/addchannel` | Add a channel ID to an existing rule |
| `/removechannel` | Remove a channel ID from a rule |
| `/addemoji` | Add an emoji reaction to a rule |
| `/removeemoji` | Remove an emoji from a rule |
| `/addtrigger` | Add a trigger to a rule |
| `/removetrigger` | Remove a trigger from a rule |
| `/togglebots` | Toggle the `ignore_bots` global setting |
| `/reloadconfig` | Reload configuration from disk |

**Permissions:** By default, only users with the **Manage Server** Discord permission can use these commands. To restrict access further, set `admin_role` or `admin_users` in the `global` section of `config.yaml`.

### Full Example

```yaml
rules:
  # React to embeds and attachments
  - channels:
      - 111111111111
    triggers:
      - type: embed
      - type: attachment
    emojis:
      - "👍"
      - "🎉"

  # Greet messages that say hello
  - channels:
      - 222222222222
    triggers:
      - type: contains
        value: "hello"
    emojis:
      - "👋"

  # React to all messages in a showcase channel
  - channels:
      - 333333333333
    triggers:
      - type: all
    emojis:
      - "❤️"

  # React when a thread is created
  - channels:
      - 444444444444
    triggers:
      - type: thread_created
    emojis:
      - "🧵"
```

## Running as a systemd Service (Linux VPS)

To run the bot as a managed service that auto-starts on reboot and restarts on crash:

### 1. Edit the unit file

Open `reactionary.service` and replace the placeholder values:

- `YOUR_USERNAME` → your Linux username on the VPS (e.g. `ubuntu`)
- `/path/to/Reactionary` → the full path where you cloned the repo (e.g. `/home/ubuntu/Reactionary`)
- Verify the Python path with `which python3` and update `ExecStart` if it differs from `/usr/bin/python3`. If you use a virtual environment, use the full path to that environment's Python binary instead (e.g. `/home/ubuntu/Reactionary/venv/bin/python`).

### 2. Install and enable the service

```bash
sudo cp reactionary.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable reactionary
sudo systemctl start reactionary
sudo systemctl status reactionary
```

`systemctl enable` registers the service to start automatically on every reboot.  
`Restart=always` ensures the bot is restarted automatically if it ever crashes.

### 3. Useful management commands

```bash
sudo systemctl stop reactionary      # Stop the bot
sudo systemctl restart reactionary   # Restart the bot
journalctl -u reactionary -f         # Tail live logs
journalctl -u reactionary -n 50      # Last 50 log lines
```

## How It Works

- The bot loads reaction rules from `config.yaml` at startup and prints a summary of loaded rules.
- Each rule defines channels to watch, triggers to match, and emojis to react with.
- When a message arrives the bot evaluates every rule whose channel list includes the message's channel (or all rules if `channels` is omitted), skipping any channels listed in `excluded_channels`.
- If `trigger_mode` is `"any"` (the default), the rule fires when **any** trigger matches. If `trigger_mode` is `"all"`, the rule fires only when **every** trigger matches.
- The `thread_created` trigger listens for new threads and reacts to the starter message. When paired with other triggers and `trigger_mode: "all"`, all non-`thread_created` triggers are also evaluated against the starter message.
- Messages from the bot itself are always ignored. Set `global.ignore_bots: true` to also ignore messages from other bots.
