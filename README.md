# Olo Wpierdolo's Gambling Casino Bot

A self-hosted Discord bot that provides a persistent, in-server casino/economy for small friend groups. Features virtual currency gambling with deathroll duels, leaderboards, and statistics.

## Features

- **Virtual Economy**: Persistent coin balance per user (no real money)
- **Deathroll Duels**: WoW-style decreasing roll 1v1 gambling
- **Daily Rewards**: Claim free coins every 24 hours
- **Leaderboards**: See the richest players
- **Statistics**: Detailed stats for each player
- **Admin Tools**: Manage balances for debugging

## Commands

### Economy
| Command | Description |
|---------|-------------|
| `/register` | Join the casino and receive 10,000 starting coins |
| `/balance` | Check your current coin balance and stats |
| `/daily` | Claim your daily reward (1,000 coins, 24h cooldown) |

### Gambling
| Command | Description |
|---------|-------------|
| `/duel_start @user <amount>` | Challenge someone to a deathroll duel |
| `/duel_cancel` | Cancel your pending duel challenge |

### Stats
| Command | Description |
|---------|-------------|
| `/stats [@user]` | View detailed statistics |
| `/leaderboard` | View top 10 richest players |

### Admin (Administrator only)
| Command | Description |
|---------|-------------|
| `/admin_add_coins @user <amount>` | Add/remove coins from a user |
| `/admin_reset_user @user` | Reset user to starting balance |
| `/admin_view_user @user` | View detailed user info |

## Setup

### Prerequisites
- Python 3.10+
- A Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))

### Installation

1. **Clone or download this repository**

2. **Create a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   .\venv\Scripts\activate   # Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp env.example .env
   ```
   
   Edit `.env` and set your Discord bot token:
   ```
   DISCORD_BOT_TOKEN=your_actual_token_here
   GUILD_ID=your_server_id_for_faster_testing  # Optional
   ```

5. **Run the bot**:
   ```bash
   python -m bot.main
   ```

### Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Enable these Privileged Gateway Intents:
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`
5. Copy the bot token to your `.env` file
6. Go to "OAuth2" > "URL Generator":
   - Select scopes: `bot`, `applications.commands`
   - Select permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`
7. Use the generated URL to invite the bot to your server

## How Deathroll Works

Deathroll is a WoW-inspired gambling game:

1. Player A challenges Player B with a bet (e.g., 50,000 coins)
2. Both players wager the same amount
3. Player A rolls 1 to bet amount (e.g., rolls 34,521)
4. Player B rolls 1 to previous roll (e.g., rolls 8,742)
5. Players alternate, each rolling 1 to previous roll
6. **Player who rolls 1 loses the entire pot!**

## Tech Stack

- **Python 3.10+** with asyncio
- **discord.py** for Discord API
- **SQLAlchemy** (async) for ORM
- **SQLite** for persistence (aiosqlite)
- **python-dotenv** for configuration

## Project Structure

```
OloWpierdolosGamblingCasinoBot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Bot entry point
│   ├── config.py            # Configuration
│   ├── database/
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── database.py      # DB connection
│   │   └── crud.py          # Database operations
│   ├── cogs/
│   │   ├── economy.py       # /register, /balance, /daily
│   │   ├── duel.py          # Deathroll game
│   │   ├── stats.py         # /stats, /leaderboard
│   │   └── admin.py         # Admin commands
│   └── utils/
│       └── helpers.py       # Utilities and exceptions
├── .env                     # Your config (git-ignored)
├── env.example              # Config template
├── requirements.txt
└── README.md
```

## Running as a Service (Linux)

Create a systemd service file `/etc/systemd/system/casino-bot.service`:

```ini
[Unit]
Description=Olo Wpierdolo's Gambling Casino Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/OloWpierdolosGamblingCasinoBot
Environment=PATH=/path/to/venv/bin
ExecStart=/path/to/venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable casino-bot
sudo systemctl start casino-bot
```

## License

This project is for personal/educational use. Not affiliated with any real gambling operations.

