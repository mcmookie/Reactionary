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

## How It Works

- The bot listens for new messages in the channel specified by `CHANNEL_ID`.
- When a message contains one or more embeds, the bot adds the configured emoji reaction to it.
- Messages without embeds and messages from the bot itself are ignored.
