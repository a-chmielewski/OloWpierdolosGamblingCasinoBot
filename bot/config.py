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
    STARTING_BALANCE: int = 10_000
    DAILY_REWARD: int = 1_000
    DAILY_COOLDOWN_HOURS: int = 24
    
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
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.DISCORD_BOT_TOKEN:
            raise ValueError("DISCORD_BOT_TOKEN is required. Set it in .env file.")


config = Config()

