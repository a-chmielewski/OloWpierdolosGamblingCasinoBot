"""Main entry point for Olo Wpierdolo's Gambling Casino Bot."""

import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

from config import config
from database.database import init_db, close_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("casino_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("casino_bot")

# Reduce noise from discord.py
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)


class CasinoBot(commands.Bot):
    """Olo Wpierdolo's Gambling Casino Bot."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",  # Fallback prefix, we use slash commands
            intents=intents,
            help_command=None,
        )
    
    async def setup_hook(self) -> None:
        """Called when the bot is starting up."""
        logger.info("Setting up bot...")
        
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Load cogs
        cog_files = [
            "cogs.economy",
            "cogs.duel",
            "cogs.slots",
            "cogs.roulette",
            "cogs.group_pot",
            "cogs.blackjack",
            "cogs.animal_race",
            "cogs.stats",
            "cogs.tier",
            "cogs.admin",
        ]
        
        for cog in cog_files:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")
        
        # Sync commands
        if config.GUILD_ID:
            # Sync to specific guild for faster testing
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced commands to guild {config.GUILD_ID}")
        else:
            # Global sync (takes up to an hour to propagate)
            await self.tree.sync()
            logger.info("Synced commands globally")
    
    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info("------")
        
        # Set activity
        activity = discord.Activity(
            type=discord.ActivityType.playing,
            name="🎰 /register to start gambling!"
        )
        await self.change_presence(activity=activity)
    
    async def close(self) -> None:
        """Clean up when bot is shutting down."""
        logger.info("Shutting down...")
        await close_db()
        await super().close()


async def main() -> None:
    """Main entry point."""
    # Validate configuration
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Create and run bot
    bot = CasinoBot()
    
    try:
        await bot.start(config.DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid Discord token. Check your DISCORD_BOT_TOKEN in .env")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())

