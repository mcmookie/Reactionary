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

The bot token can be set in **either** `.env` (as `DISCORD_TOKEN`) or in `config.yaml` (as `discord_token`). The environment variable takes precedence.

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
discord_token: "your_bot_token_here"   # optional if set in .env

rules:
  - channels:          # list of channel IDs (omit to match all channels)
      - 111111111111
    triggers:          # at least one trigger must match
      - type: embed
    emojis:            # reactions to add when a trigger matches
      - "👍"
      - "🎉"
```

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

A rule fires when **any** of its triggers match (logical OR). You can combine multiple triggers in a single rule:

```yaml
rules:
  - channels:
      - 111111111111
    triggers:
      - type: embed
      - type: attachment
      - type: has_link
    emojis:
      - "🔗"
```

If `channels` is omitted the rule applies to **all** channels.

### Full Example

```yaml
discord_token: "your_bot_token_here"

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

- The bot loads reaction rules from `config.yaml` at startup.
- Each rule defines channels to watch, triggers to match, and emojis to react with.
- When a message arrives the bot evaluates every rule whose channel list includes the message's channel (or all rules if `channels` is omitted).
- If **any** trigger in a rule matches, the bot adds all of that rule's emojis as reactions.
- The `thread_created` trigger listens for new threads and reacts to the starter message.
- Messages from the bot itself are always ignored.
