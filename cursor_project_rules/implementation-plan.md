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

## Phase 6: Slots Game

### 6.1 Configuration
**Status:** Done

Updated `bot/config.py` with slots constants:
- SLOT_SYMBOLS: ["🍒", "🍋", "⭐", "💎", "💀"]
- SLOT_WEIGHTS: Probability weights for weighted random selection
- Payout multipliers for different combinations (jackpot 10x, triple 5x/3x, double 2x, death curse -2x)

### 6.2 Slots cog
**Status:** Done

Created `bot/cogs/slots.py` with:
- `/slots <bet>`: Play the slot machine
- Validation: user registered, positive bet, sufficient balance
- Weighted random symbol generation using `random.choices()`
- Payout calculation:
  - Triple diamonds (💎💎💎): 10x jackpot
  - Triple stars (⭐⭐⭐): 5x
  - Triple lemons/cherries: 3x
  - Any two matching: 2x
  - Triple skulls (💀💀💀): LOSE 2x (death curse)
  - No match: lose bet
- Balance updates with SLOTS_WIN/SLOTS_LOSS transaction reasons
- Rich embeds with color coding (gold for jackpot, green for wins, red for losses)
- Slot machine visual display with symbols

### 6.3 Statistics
**Status:** Done

Updated `bot/database/crud.py`:
- Added slots stats queries to `get_user_game_stats()`
- Tracks slots_played, slots_won, slots_lost
- Includes slots transactions in biggest win/loss calculations

Updated `bot/cogs/stats.py`:
- Added 🎰 Slot Machine section to `/stats` command
- Displays games played, won, lost, and win rate

### 6.4 Documentation
**Status:** Done

Updated `README.md`:
- Added slot machine to features list
- Added `/slots <bet>` to gambling commands table
- Added "How Slots Work" section with payout rules table
- Updated project structure to include slots.py

---

## Phase 7: Roulette Game

### 7.1 Configuration
**Status:** Done

Updated `bot/config.py` with roulette constants:
- ROULETTE_RED_CHANCE: 18 (out of 37)
- ROULETTE_BLACK_CHANCE: 18 (out of 37)
- ROULETTE_GREEN_CHANCE: 1 (out of 37)
- ROULETTE_PAYOUT_RED_BLACK: 2x payout
- ROULETTE_PAYOUT_GREEN: 14x payout

### 7.2 Roulette cog
**Status:** Done

Created `bot/cogs/roulette.py` with:
- `/roulette <bet> <choice>`: Play roulette with color-based betting
- Color choices: red, black, green with app_commands.Choice for user selection
- Validation: user registered, positive bet, sufficient balance
- Weighted random color selection using probabilities (18/18/1 out of 37)
- Payout calculation: 2x for red/black, 14x for green
- Animated wheel spin with suspenseful reveal
- Rich embeds with color-coded results and number display (0-36)
- Balance updates with ROULETTE_WIN/ROULETTE_LOSS transaction reasons

### 7.3 Statistics
**Status:** Done

Updated `bot/database/crud.py`:
- Added roulette stats queries to `get_user_game_stats()`
- Tracks roulette_played, roulette_won, roulette_lost
- Includes roulette transactions in biggest win/loss calculations

Updated `bot/cogs/stats.py`:
- Added 🎡 Roulette section to `/stats` command
- Displays games played, won, lost, and win rate

Updated `bot/main.py`:
- Added "cogs.roulette" to cog loading list

### 7.4 Documentation
**Status:** Done

Updated `README.md`:
- Added roulette to features list
- Added `/roulette <bet> <choice>` to gambling commands table
- Added "How Roulette Works" section with color choices, probabilities, and payout rules
- Updated project structure to include roulette.py

---

## Phase 8: Group Pot High-Roll Game

### 8.1 Group Pot Cog
**Status:** Done

Created `bot/cogs/group_pot.py` with:
- `/group_start <amount>`: Create GROUP_POT GameSession in PENDING state
  - Stores bet amount in game data (JSON)
  - Creator auto-joins as first participant
  - Validation for registered user, positive amount, sufficient balance
  - No active group pot game per channel at a time
- `/group_join`: Join pending game in same channel
  - Validates user registration, balance, not already joined
  - Creates DuelParticipant record for each joiner
  - Updates game embed showing all participants
- `/group_leave`: Leave pending game before it starts
  - Removes participant from game
  - Cancels game if creator leaves or no participants remain
- `/group_start_roll`: Begin the game (creator only)
  - Validation: minimum 2 participants, game still pending
  - Rolls for each participant: randint(1, amount)
  - Stores rolls in DuelParticipant.result_value
  - Determines winner (highest roll) and loser (lowest roll)
  - Handles ties with automatic re-rolls among tied players
  - Calculates transfer amount: highest_roll - lowest_roll
  - Transfers money from loser to winner (no upfront deduction)
  - Creates transactions with GROUP_POT_WIN and GROUP_POT_LOSS
  - Animated roll reveals with dramatic pauses
  - Final summary showing all rolls, winner, and transfer amount

### 8.2 Statistics
**Status:** Done

Updated `bot/database/crud.py`:
- Added group pot stats queries to `get_user_game_stats()`
- Tracks group_pot_played, group_pot_won, group_pot_lost
- Includes group pot transactions in biggest win/loss calculations

Updated `bot/cogs/stats.py`:
- Added 🎲 Group Pot section to `/stats` command
- Displays games played, won, lost, and win rate

Updated `bot/main.py`:
- Added "cogs.group_pot" to cog loading list

### 8.3 Documentation
**Status:** Done

Updated `README.md`:
- Added "Group Pot High-Roll" to features list
- Added group pot commands to gambling table:
  - `/group_start <amount>` - Start a group pot game
  - `/group_join` - Join pending game
  - `/group_leave` - Leave pending game
  - `/group_start_roll` - Begin the game (creator only)
- Added "How Group Pot Works" section explaining:
  - Multi-player game flow
  - Roll mechanics (1 to bet amount)
  - Winner/loser determination
  - Payout calculation (difference between highest and lowest)
  - No upfront deduction - only winner and loser affected
  - Tie-breaking with re-rolls
  - Channel-based game restrictions
- Updated project structure to include group_pot.py

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

