# Implementation Plan - Olo Wpierdolo's Gambling Casino Bot

## Phase 1: Project Setup and Database Layer

### 1.1 Create project files and dependencies
**Status:** Done

Created the following files:
- `requirements.txt` with discord.py, SQLAlchemy, python-dotenv, aiosqlite
- `env.example` with template for DISCORD_BOT_TOKEN, DATABASE_URL, GUILD_ID
- `.gitignore` with standard Python ignores plus .env and *.db

### 1.2 Configuration module
**Status:** Done

Created `bot/config.py` with Config class loading environment variables and constants:
- Discord token, guild ID for dev
- Economy constants (starting balance: 10,000, daily: 1,000)
- Game constants (duel timeout, roll delay)

### 1.3 Database models
**Status:** Done

Created `bot/database/models.py` with SQLAlchemy models:
- User: discord_id, name, balance, lifetime_earned, lifetime_lost, last_daily, timestamps
- Transaction: user_id, amount, reason (enum), ref_game_id, timestamp
- GameSession: type, status, created_by_user_id, channel_id, data (JSON), timestamps
- DuelParticipant: game_id, user_id, bet_amount, result_value, is_winner

### 1.4 Database connection
**Status:** Done

Created `bot/database/database.py` with:
- Async SQLAlchemy engine with SQLite (aiosqlite)
- Session factory and async context manager
- init_db() and close_db() functions

### 1.5 CRUD operations
**Status:** Done

Created `bot/database/crud.py` with comprehensive operations:
- User: get_or_create, update_balance, get_by_discord_id, can_claim_daily
- Transaction: create_transaction (via update_balance)
- GameSession: create, update_status, get_active_for_user
- Leaderboard queries: get_richest_users, get_user_rank
- Stats queries: get_user_game_stats

---

## Phase 2: Bot Core and Economy Commands

### 2.1 Bot main entry
**Status:** Done

Created `bot/main.py` with:
- CasinoBot class extending commands.Bot
- Intents configuration (members, message_content)
- Cog loading system
- on_ready event with activity status
- Command sync (guild or global)
- Logging setup to console and file

### 2.2 Economy cog
**Status:** Done

Created `bot/cogs/economy.py` with commands:
- `/register`: Create user with 10,000 starting coins, prevents duplicates
- `/balance`: Shows current balance, lifetime earned/lost, net profit
- `/daily`: Awards 1,000 coins with 24h cooldown enforcement

---

## Phase 3: Deathroll Duel Game

### 3.1 Duel cog
**Status:** Done

Created `bot/cogs/duel.py` with:
- `/duel_start @opponent <amount>`: Challenge with validation (registered, balance, no active game)
- DuelChallengeView with Accept/Decline buttons (60s timeout)
- Automated roll sequence with dramatic delays (1.5s between rolls)
- Roll announcements with emojis based on roll value
- Death roll detection and game finalization
- `/duel_cancel`: Cancel pending challenges

### 3.2 Duel game logic
**Status:** Done

Implemented in duel cog:
- _run_duel(): Core game loop with alternating players
- _finalize_duel(): Balance transfers, participant updates, victory message
- Roll history display in victory embed
- Per-user locking via helpers.py

---

## Phase 4: Stats and Leaderboards

### 4.1 Stats cog
**Status:** Done

Created `bot/cogs/stats.py` with:
- `/leaderboard`: Top 10 richest with medals, net profit, requester rank
- `/stats [@user]`: Detailed stats including balance, rank, net profit, duels played/won/lost, win rate, biggest win/loss

---

## Phase 5: Admin Commands

### 5.1 Admin cog
**Status:** Done

Created `bot/cogs/admin.py` with:
- is_admin() decorator checking bot owner or administrator permission
- `/admin_add_coins @user <amount>`: Add/remove coins with transaction logging
- `/admin_reset_user @user`: Reset to starting balance
- `/admin_view_user @user`: View detailed user info (IDs, balances, timestamps)
- Error handler for permission denied

---

## Utilities

### helpers.py
**Status:** Done

Created `bot/utils/helpers.py` with:
- UserLockManager class for per-user asyncio locks
- format_coins() for displaying amounts
- Custom exceptions: NotRegisteredException, InsufficientFundsException, InvalidBetException, NoActiveGameException, GameAlreadyActiveException

---

## Documentation

### README.md
**Status:** Done

Created comprehensive README with:
- Feature list
- Command reference tables
- Setup instructions (venv, dependencies, Discord bot setup)
- Deathroll game explanation
- Tech stack and project structure
- Systemd service example for production

---

## Summary

All phases completed. The bot is ready to run with:
1. `cp env.example .env` and configure DISCORD_BOT_TOKEN
2. `pip install -r requirements.txt`
3. `python -m bot.main`

