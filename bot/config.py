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
    
    # Slots constants
    SLOT_SYMBOLS: list[str] = ["🍒", "🍋", "⭐", "💎", "💀"]
    SLOT_WEIGHTS: list[int] = [30, 25, 20, 15, 10]  # Probability weights
    SLOT_PAYOUT_TRIPLE_JACKPOT: int = 10  # 💎💎💎
    SLOT_PAYOUT_TRIPLE_HIGH: int = 5      # ⭐⭐⭐
    SLOT_PAYOUT_TRIPLE_MID: int = 3       # 🍋🍋🍋 or 🍒🍒🍒
    SLOT_PAYOUT_DOUBLE: int = 2           # Any 2 matching
    SLOT_PAYOUT_DEATH: int = -2           # 💀💀💀 (lose double)
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.DISCORD_BOT_TOKEN:
            raise ValueError("DISCORD_BOT_TOKEN is required. Set it in .env file.")


config = Config()

