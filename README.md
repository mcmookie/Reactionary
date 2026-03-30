# Reactionary

A single-purpose Discord bot that automatically reacts to messages containing embeds in a specified channel.

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application.
2. Under **Bot**, create a bot user and copy the token.
3. Enable the **Message Content Intent** under **Privileged Gateway Intents**.
4. Invite the bot to your server with the `bot` scope and the `Add Reactions` + `Read Messages` permissions.

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable        | Description                                      |
|-----------------|--------------------------------------------------|
| `DISCORD_TOKEN` | Your bot token from the Developer Portal         |
| `CHANNEL_ID`    | The ID of the channel to monitor                 |
| `REACTION_EMOJI`| The emoji to react with (default: `👍`)          |

To get a channel ID, enable **Developer Mode** in Discord settings, then right-click the channel and select **Copy ID**.

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Bot

```bash
python bot.py
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

- The bot listens for new messages in the channel specified by `CHANNEL_ID`.
- When a message contains one or more embeds, the bot adds the configured emoji reaction to it.
- Messages without embeds and messages from the bot itself are ignored.
