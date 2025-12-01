"""Economy cog - User registration, balance, and daily rewards."""

import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from database.database import get_session
from database.crud import (
    get_user_by_discord_id,
    get_or_create_user,
    update_user_balance,
    update_last_daily,
    can_claim_daily,
)
from database.models import TransactionReason
from utils.helpers import format_coins, get_user_lock

logger = logging.getLogger(__name__)


class Economy(commands.Cog):
    """Economy commands for registration, balance, and daily rewards."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="register", description="Register for the casino and receive starting coins")
    async def register(self, interaction: discord.Interaction) -> None:
        """Register a new user in the casino."""
        async with get_user_lock(interaction.user.id):
            async with get_session() as session:
                user, created = await get_or_create_user(
                    session,
                    discord_id=interaction.user.id,
                    name=interaction.user.display_name,
                )
                
                if created:
                    embed = discord.Embed(
                        title="🎰 Welcome to Olo Wpierdolo's Gambling Casino!",
                        description=(
                            f"You have been registered successfully!\n\n"
                            f"**Starting Balance:** {format_coins(config.STARTING_BALANCE)}\n\n"
                            f"Use `/daily` to claim your daily reward.\n"
                            f"Use `/balance` to check your coins.\n"
                            f"Use `/duel_start @user <amount>` to challenge someone!"
                        ),
                        color=discord.Color.green(),
                    )
                    embed.set_thumbnail(url=interaction.user.display_avatar.url)
                else:
                    embed = discord.Embed(
                        title="Already Registered",
                        description=(
                            f"You are already registered!\n\n"
                            f"**Current Balance:** {format_coins(user.balance)}"
                        ),
                        color=discord.Color.blue(),
                    )
                
                await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="balance", description="Check your current coin balance")
    async def balance(self, interaction: discord.Interaction) -> None:
        """Show user's current balance and stats summary."""
        async with get_session() as session:
            user = await get_user_by_discord_id(session, interaction.user.id)
            
            if not user:
                embed = discord.Embed(
                    title="❌ Not Registered",
                    description="You are not registered yet! Use `/register` to join the casino.",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            net_profit = user.lifetime_earned - user.lifetime_lost
            net_color = discord.Color.green() if net_profit >= 0 else discord.Color.red()
            net_symbol = "+" if net_profit >= 0 else ""
            
            embed = discord.Embed(
                title=f"💰 {interaction.user.display_name}'s Balance",
                color=net_color,
            )
            embed.add_field(
                name="Current Balance",
                value=format_coins(user.balance),
                inline=False,
            )
            embed.add_field(
                name="Lifetime Earned",
                value=format_coins(user.lifetime_earned),
                inline=True,
            )
            embed.add_field(
                name="Lifetime Lost",
                value=format_coins(user.lifetime_lost),
                inline=True,
            )
            embed.add_field(
                name="Net Profit",
                value=f"🪙 {net_symbol}{net_profit:,}",
                inline=True,
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="daily", description="Claim your daily coin reward")
    async def daily(self, interaction: discord.Interaction) -> None:
        """Claim daily reward with 24h cooldown."""
        async with get_user_lock(interaction.user.id):
            async with get_session() as session:
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                if not user:
                    embed = discord.Embed(
                        title="❌ Not Registered",
                        description="You are not registered yet! Use `/register` to join the casino.",
                        color=discord.Color.red(),
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                can_claim, time_remaining = await can_claim_daily(session, user.id)
                
                if not can_claim:
                    hours, remainder = divmod(int(time_remaining.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    embed = discord.Embed(
                        title="⏰ Daily Already Claimed",
                        description=(
                            f"You have already claimed your daily reward!\n\n"
                            f"**Time until next claim:** {hours}h {minutes}m {seconds}s"
                        ),
                        color=discord.Color.orange(),
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Grant daily reward
                await update_user_balance(
                    session,
                    user_id=user.id,
                    amount=config.DAILY_REWARD,
                    reason=TransactionReason.DAILY_REWARD,
                )
                await update_last_daily(session, user.id)
                
                # Refresh user data
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                embed = discord.Embed(
                    title="🎁 Daily Reward Claimed!",
                    description=(
                        f"You received {format_coins(config.DAILY_REWARD)}!\n\n"
                        f"**New Balance:** {format_coins(user.balance)}\n\n"
                        f"Come back in 24 hours for more!"
                    ),
                    color=discord.Color.gold(),
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                
                await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Economy(bot))

