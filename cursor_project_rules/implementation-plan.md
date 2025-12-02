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

## Phase 9: Blackjack Game

### 9.1 Database Models
**Status:** Done

Updated `bot/database/models.py`:
- Added BLACKJACK to GameType enum
- Added BLACKJACK_WIN and BLACKJACK_LOSS to TransactionReason enum
- Reused existing GameSession and DuelParticipant models for game tracking

### 9.2 Configuration
**Status:** Done

Updated `bot/config.py` with Blackjack constants:
- BLACKJACK_JOIN_TIMEOUT_SECONDS: 45 (time for players to join multiplayer)
- BLACKJACK_ACTION_TIMEOUT_SECONDS: 45 (time for each player action)
- BLACKJACK_CARD_DELAY_SECONDS: 1.0 (dramatic delay between cards)
- BLACKJACK_NATURAL_PAYOUT: 1.5 (3:2 payout for natural blackjack)
- BLACKJACK_MIN_BET: 100 (minimum bet amount)
- BLACKJACK_DEALER_STAND_VALUE: 17 (dealer stands on 17+)

### 9.3 Card System Utilities
**Status:** Done

Created `bot/utils/card_utils.py` with:
- Card class with rank, suit, and emoji representation
- Deck class with shuffling and dealing (52-card standard deck)
- Hand class with card tracking, value calculation, ace handling
- Card emoji mappings for all 52 cards (A❤️, 2❤️, ..., K♠️)
- Helper functions: format_hand_display(), calculate_winner()
- Support for blackjack rules: bust detection, natural blackjack, soft aces

### 9.4 Blackjack Cog
**Status:** Done

Created `bot/cogs/blackjack.py` with:
- `/blackjack <bet>`: Start a blackjack game with bet validation
- GameModeView: Buttons for Solo vs Multiplayer choice
- JoinGameView: Button for other players to join multiplayer games
- Full game flow:
  1. Validate user registration and balance
  2. Choose Solo or Multiplayer mode
  3. For multiplayer: wait 45 seconds for players to join
  4. Deal initial cards (2 to each player, 2 to dealer with one face-down)
  5. Each player takes turn sequentially with emoji reactions:
     - 👊 Hit - Draw another card
     - ✋ Stand - Keep current hand
     - 💰 Double Down - Double bet and take one final card (first action only)
     - ✂️ Split - Placeholder for future feature
  6. Dealer reveals hole card and plays (hits until 17+)
  7. Calculate winners and payouts:
     - Natural blackjack: 3:2 payout (2.5x bet)
     - Regular win: 2:1 payout (2x bet)
     - Push (tie): Return bet
     - Loss: Lose bet
  8. Update balances with transactions
- Animated card dealing with delays for dramatic effect
- Rich embeds with color coding (gold for blackjack, green for wins, red for losses)
- Auto-stand on player timeout
- Special handling for dealer blackjack

### 9.5 Statistics
**Status:** Done

Updated `bot/database/crud.py`:
- Added blackjack stats queries to `get_user_game_stats()`
- Tracks blackjack_played, blackjack_won, blackjack_lost
- Includes blackjack transactions in biggest win/loss calculations

Updated `bot/cogs/stats.py`:
- Added 🃏 Blackjack section to `/stats` command
- Displays games played, won, lost, and win rate

Updated `bot/main.py`:
- Added "cogs.blackjack" to cog loading list

### 9.6 Features Implemented
- Solo and multiplayer modes (each player vs dealer independently)
- All players in multiplayer game bet same amount
- Emoji reaction-based controls for player actions
- Full blackjack rules with proper ace handling
- Natural blackjack bonus (3:2 payout)
- Double Down feature
- Visual card emojis for all 52 cards
- Dramatic animated dealing and turn progression
- Comprehensive statistics tracking
- Integration with existing economy and database systems

---

## Phase 10: Animal Racing Game

### 10.1 Database Models
**Status:** Done

Updated `bot/database/models.py`:
- Added ANIMAL_RACE to GameType enum
- Added ANIMAL_RACE_WIN and ANIMAL_RACE_LOSS to TransactionReason enum

### 10.2 Configuration
**Status:** Done

Updated `bot/config.py` with animal racing constants:
- RACE_JOIN_TIMEOUT_SECONDS: 30 (time window for players to join)
- RACE_TRACK_LENGTH: 100 (total distance for race)
- RACE_UPDATE_INTERVAL: 0.8 (seconds between progress updates)
- RACE_MIN_BET: 100 (minimum bet amount)
- RACE_PROGRESS_BAR_LENGTH: 10 (visual progress bar length)
- RACE_RACERS: List of 5 racers with emoji, name, and speed ranges:
  - Turtle 🐢: [1, 4] (slow but steady)
  - Hare 🐇: [3, 8] (usually fast, inconsistent)
  - Chicken 🐓: [2, 6] (middle ground)
  - Dino 🦖: [2, 7] (unpredictable)
  - Kubica :kubica: : [1, 8] (widest range for comedy)

### 10.3 Race Utilities
**Status:** Done

Created `bot/utils/race_utils.py` with:
- Racer class: Manages individual racer with name, emoji, speed range, position
- RaceTrack class: Manages all racers, updates positions, checks for winner
- format_progress_bar(): Creates visual progress bar using Unicode blocks (▓░)
- format_race_display(): Formats racer display line with emoji, name, progress bar, percentage
- Helper functions: get_racer_config_by_emoji(), get_racer_config_by_name()

### 10.4 Animal Race Cog
**Status:** Done

Created `bot/cogs/animal_race.py` with:
- `/race_start <bet>`: Start an animal racing game
  - Validation: user registered, positive bet >= min, sufficient balance
  - Create GameSession with ANIMAL_RACE type
  - Display racer roster with emojis, names, and speed ranges
  - Show JoinRaceView with buttons for each racer (30s timeout)
  - Store player racer choices in game data JSON
- JoinRaceView: Discord UI with 5 buttons (one per racer)
  - Validates user registration, balance, not already joined
  - Adds participant with chosen racer stored in game data
  - Updates message showing who joined
  - Allows multiple players to bet on same racer
- _run_race(): Execute the race with animation
  - Initialize RaceTrack with 5 racers
  - Loop until winner reaches track length (100):
    - Update all racer positions (random within speed range)
    - Send embed with progress bars for all 5 racers
    - Highlight racers that players bet on with 💰
    - Sleep for RACE_UPDATE_INTERVAL (0.8s)
  - Determine winner and calculate pot (total bets from all players)
  - Distribute winnings to players who bet on winner
  - Split pot equally if multiple players bet on same winner
  - Deduct bet from losers, add profit to winners
  - Create transactions with ANIMAL_RACE_WIN/LOSS reasons
  - Show final results with dramatic embed showing standings and payouts

### 10.5 Statistics
**Status:** Done

Updated `bot/database/crud.py`:
- Added animal race stats queries to `get_user_game_stats()`
- Tracks animal_race_played, animal_race_won, animal_race_lost
- Includes animal race transactions in biggest win/loss calculations

Updated `bot/cogs/stats.py`:
- Added 🏁 Animal Racing section to `/stats` command
- Displays games played, won, lost, and win rate

Updated `bot/main.py`:
- Added "cogs.animal_race" to cog loading list

### 10.6 Features Implemented
- Multi-player racing game (1-5 players)
- Winner-takes-all pot system with pot splitting for multiple winners
- 5 unique racers with different speed characteristics
- Custom emoji support (:kubica:) integrated into racer list
- Animated race with real-time progress bars
- Visual progress indicators using Unicode blocks (▓░)
- Random speed within configured ranges creates unpredictable outcomes
- Hilarious scenarios where slow racers can beat fast ones
- 30-second join window with button-based racer selection
- Full statistics tracking and display
- Integration with existing economy and database systems

---

## Phase 11: Daily/Hourly Streak System

### 11.1 Database Models
**Status:** Done

Updated `bot/database/models.py`:
- Added `daily_streak`, `daily_streak_best`, `hourly_streak`, `hourly_streak_best` fields to User model
- Added `DAILY_STREAK_INSURANCE` and `HOURLY_STREAK_INSURANCE` to TransactionReason enum

### 11.2 Configuration
**Status:** Done

Updated `bot/config.py` with streak constants:
- DAILY_STREAK_BONUS_PER_DAY: 0.10 (+10% per consecutive day)
- DAILY_STREAK_DAY7_REWARD: 20,000 (capped reward at day 7+)
- DAILY_STREAK_MAX_BONUS_DAY: 7 (day at which bonus caps)
- DAILY_STREAK_INSURANCE_COST: 25,000 (cost to recover broken daily streak)
- HOURLY_STREAK_BONUS_PER_HOUR: 0.10 (+10% per consecutive hour)
- HOURLY_STREAK_MAX_REWARD: 1,500 (capped reward at hour 5+)
- HOURLY_STREAK_MAX_BONUS_HOUR: 5 (hour at which bonus caps)
- HOURLY_STREAK_MISSED_THRESHOLD: 2 (missed hourly windows to reset streak)
- HOURLY_STREAK_INSURANCE_COST: 2,500 (cost to recover broken hourly streak)

### 11.3 CRUD Operations
**Status:** Done

Added streak functions to `bot/database/crud.py`:
- `calculate_daily_reward()`: Computes reward based on streak (Day 1: 10k, Days 2-6: +10%, Day 7+: 20k)
- `calculate_hourly_reward()`: Computes reward based on streak (Hour 1: 1k, Hours 2-4: +10%, Hour 5+: 1.5k)
- `check_daily_streak_status()`: Determines if daily streak is broken and missed periods
- `check_hourly_streak_status()`: Determines if hourly streak is broken (2+ missed hours)
- `update_daily_streak()`: Updates streak on claim, tracks personal best
- `update_hourly_streak()`: Updates streak on claim, tracks personal best
- `purchase_daily_streak_insurance()`: Deducts 25k coins to recover broken daily streak
- `purchase_hourly_streak_insurance()`: Deducts 2.5k coins to recover broken hourly streak
- `get_user_streak_info()`: Returns comprehensive streak status for display

### 11.4 Economy Cog Updates
**Status:** Done

Updated `bot/cogs/economy.py` with enhanced commands:
- `/daily`: Now shows streak info with fire emojis (🔥), bonus percentage, personal best notifications
  - Day 7 celebration with special message
  - Broken streak warning with previous streak display
  - Next day reward preview
- `/hourly`: Now shows streak info with timer emojis (⏱️), bonus percentage, personal best notifications
  - Warning about streak reset threshold
  - Next hour reward preview
- `/streak`: New command to view detailed streak status for both daily and hourly
  - Shows current/best streaks, status (active/broken), next reward amounts
  - Insurance cost display for broken streaks
- `/streak_save <daily|hourly>`: New command to purchase streak insurance
  - Validates streak is actually broken
  - Checks sufficient balance
  - Deducts cost and restores streak continuity

### 11.5 Database Migration
**Status:** Done

Created `bot/migrations/add_streak_columns.py`:
- Adds daily_streak, daily_streak_best, hourly_streak, hourly_streak_best columns
- Safe to run multiple times (skips existing columns)
- Sets default values to 0 for all existing users

### 11.6 Features Implemented
- Progressive daily rewards: Day 1 (10k), Days 2-6 (+10% each), Day 7+ (20k cap)
- Progressive hourly rewards: Hour 1 (1k), Hours 2-4 (+10% each), Hour 5+ (1.5k cap)
- Daily streak resets if more than one daily period is missed
- Hourly streak resets after 2 consecutive missed hourly windows
- Personal best tracking for both streaks
- Streak insurance to recover broken streaks (25k daily, 2.5k hourly)
- Visual flair with scaling fire/timer emojis based on streak length
- Broken streak warnings with insurance option display
- Economy-balanced caps prevent infinite inflation

---

## Summary

All phases completed. The bot is ready to run with:
1. `cp env.example .env` and configure DISCORD_BOT_TOKEN
2. `pip install -r requirements.txt`
3. `python -m bot.main`

