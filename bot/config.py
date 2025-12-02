"""Configuration module - loads settings from environment variables."""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Config:
    """Bot configuration loaded from environment variables."""
    
    # Discord
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    GUILD_ID: int | None = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./casino.db")
    
    # Economy constants
    STARTING_BALANCE: int = 50_000
    DAILY_REWARD: int = 10_000
    DAILY_RESET_HOUR: int = 3  # Daily resets at 3 AM Warsaw time
    HOURLY_REWARD: int = 1_000
    TIMEZONE: str = "Europe/Warsaw"
    
    # Daily Streak constants
    DAILY_STREAK_BONUS_PER_DAY: float = 0.10  # +10% per day (days 2-6)
    DAILY_STREAK_DAY7_REWARD: int = 20_000    # Fixed reward at day 7+
    DAILY_STREAK_MAX_BONUS_DAY: int = 7       # Day at which bonus caps
    DAILY_STREAK_INSURANCE_COST: int = 25_000 # Cost to recover broken daily streak
    
    # Hourly Streak constants
    HOURLY_STREAK_BONUS_PER_HOUR: float = 0.10  # +10% per consecutive hour (hours 2-4)
    HOURLY_STREAK_MAX_REWARD: int = 1_500       # Fixed reward at hour 5+
    HOURLY_STREAK_MAX_BONUS_HOUR: int = 5       # Hour at which bonus caps
    HOURLY_STREAK_MISSED_THRESHOLD: int = 2    # Number of missed hourly windows to reset streak
    HOURLY_STREAK_INSURANCE_COST: int = 2_500  # Cost to recover broken hourly streak
    
    # Game constants
    DUEL_TIMEOUT_SECONDS: int = 60  # Time to accept a duel challenge
    ROLL_DELAY_SECONDS: float = 1.5  # Delay between rolls for drama
    
    # Slots constants (5 reels)
    SLOT_SYMBOLS: list[str] = ["🍒", "🍋", "⭐", "💎", "💀"]
    SLOT_WEIGHTS: list[int] = [35, 30, 20, 10, 5]  # Probability weights (harder to win)
    SLOT_PAYOUT_FIVE_JACKPOT: int = 777   # 💎💎💎💎💎 (mega jackpot! 7️⃣7️⃣7️⃣)
    SLOT_PAYOUT_FIVE_HIGH: int = 20       # ⭐⭐⭐⭐⭐
    SLOT_PAYOUT_FIVE_MID: int = 10        # 🍋🍋🍋🍋🍋 or 🍒🍒🍒🍒🍒
    SLOT_PAYOUT_FOUR_MATCH: int = 5       # Any 4 matching
    SLOT_PAYOUT_THREE_MATCH: int = 2      # Any 3 matching
    SLOT_PAYOUT_DEATH: int = -3           # 💀💀💀💀💀 (lose triple!)
    
    # Roulette constants (American/European wheel simulation)
    ROULETTE_RED_CHANCE: int = 18         # Red slots out of 37
    ROULETTE_BLACK_CHANCE: int = 18       # Black slots out of 37
    ROULETTE_GREEN_CHANCE: int = 1        # Green (0) slot out of 37
    ROULETTE_PAYOUT_RED_BLACK: int = 2    # 2x payout for red/black
    ROULETTE_PAYOUT_GREEN: int = 14       # 14x payout for green
    
    # Blackjack constants
    BLACKJACK_JOIN_TIMEOUT_SECONDS: int = 45    # Time window for players to join
    BLACKJACK_ACTION_TIMEOUT_SECONDS: int = 45  # Time for each player action
    BLACKJACK_CARD_DELAY_SECONDS: float = 1.0   # Dramatic delay between cards
    BLACKJACK_NATURAL_PAYOUT: float = 1.5       # 3:2 payout for natural blackjack (2.5x total)
    BLACKJACK_MIN_BET: int = 100                # Minimum bet amount
    BLACKJACK_DEALER_STAND_VALUE: int = 17      # Dealer stands on 17+
    
    # Animal Racing constants
    RACE_JOIN_TIMEOUT_SECONDS: int = 30         # Time window for players to join
    RACE_TRACK_LENGTH: int = 100                # Total distance for race
    RACE_UPDATE_INTERVAL: float = 0.8           # Seconds between progress updates
    RACE_MIN_BET: int = 100                     # Minimum bet amount
    RACE_PROGRESS_BAR_LENGTH: int = 10          # Visual progress bar length
    # Racer configurations: name, emoji, min_speed, max_speed
    RACE_RACERS: list[dict] = [
        {"name": "Turtle", "emoji": "🐢", "min_speed": 1, "max_speed": 4},  # Slow but steady
        {"name": "Hare", "emoji": "🐇", "min_speed": 3, "max_speed": 8},  # Fast but inconsistent
        {"name": "Chicken", "emoji": "🐓", "min_speed": 2, "max_speed": 6},  # Middle ground
        {"name": "Dino", "emoji": "🦖", "min_speed": 2, "max_speed": 7},  # Unpredictable
        {"name": "Kubica", "emoji": ":kubica:", "min_speed": 1, "max_speed": 8},  # Wildcard - widest range
    ]
    
    # Progressive Bet Limits (Tier System)
    XP_DIVISOR: int = 10                        # Wager amount / 10 = XP gained
    ENABLE_BET_LIMITS: bool = True              # Enable progressive bet limits
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.DISCORD_BOT_TOKEN:
            raise ValueError("DISCORD_BOT_TOKEN is required. Set it in .env file.")


config = Config()

