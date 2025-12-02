"""Tier cog - View progression and tier information."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.database import get_session
from database.crud import get_user_by_discord_id
from utils.helpers import format_coins
from utils.tier_system import (
    get_balance_tier,
    get_level_tier,
    get_max_bet_limit,
    get_xp_progress,
    get_balance_progress,
    get_next_tier,
    format_tier_badge,
)

logger = logging.getLogger(__name__)


class Tier(commands.Cog):
    """Tier progression and information commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _create_progress_bar(self, progress: float, length: int = 10) -> str:
        """Create a visual progress bar."""
        filled = int((progress / 100.0) * length)
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}] {progress:.1f}%"
    
    async def _display_tier_info(self, interaction: discord.Interaction) -> None:
        """Core logic to display user's tier information and progression."""
        async with get_session() as session:
            user = await get_user_by_discord_id(session, interaction.user.id)
            
            if not user:
                await interaction.response.send_message(
                    "❌ You are not registered! Use `/register` first.",
                    ephemeral=True,
                )
                return
            
            # Get tier information
            balance_tier = get_balance_tier(user.balance)
            level_tier = get_level_tier(user.experience_points)
            max_bet = get_max_bet_limit(user.balance, user.experience_points)
            
            # Get progress information
            xp_in_tier, xp_needed, xp_progress = get_xp_progress(user.experience_points)
            balance_in_tier, balance_needed, balance_progress = get_balance_progress(user.balance)
            
            # Determine limiting factor
            is_balance_limiting = balance_tier.max_bet < level_tier.max_bet
            limiting_tier = balance_tier if is_balance_limiting else level_tier
            
            # Create embed
            embed = discord.Embed(
                title=f"🎯 Tier Progression - {interaction.user.display_name}",
                color=discord.Color.blue(),
            )
            
            # Current Status
            embed.add_field(
                name="📊 Current Status",
                value=(
                    f"**Balance:** {format_coins(user.balance)}\n"
                    f"**Experience:** {user.experience_points:,} XP (Level {user.level})\n"
                    f"**Current Max Bet:** {format_coins(max_bet)}"
                ),
                inline=False,
            )
            
            # Balance Tier Progress
            next_balance_tier = get_next_tier(user.balance) if balance_tier.max_balance else None
            balance_status = f"{format_tier_badge(balance_tier)}"
            if next_balance_tier:
                balance_status += f"\n**Progress to {format_tier_badge(next_balance_tier)}:**\n"
                balance_status += f"{self._create_progress_bar(balance_progress)}\n"
                balance_status += f"{format_coins(user.balance)} / {format_coins(balance_tier.max_balance)}"
            else:
                balance_status += "\n✨ **MAX TIER REACHED!**"
            
            embed.add_field(
                name="💰 Balance Tier",
                value=balance_status,
                inline=True,
            )
            
            # Level Tier Progress
            next_level_tier = get_next_tier(user.experience_points) if level_tier.max_xp else None
            level_status = f"{format_tier_badge(level_tier)}"
            if next_level_tier:
                level_status += f"\n**Progress to {format_tier_badge(next_level_tier)}:**\n"
                level_status += f"{self._create_progress_bar(xp_progress)}\n"
                level_status += f"{user.experience_points:,} / {level_tier.max_xp:,} XP"
            else:
                level_status += "\n✨ **MAX TIER REACHED!**"
            
            embed.add_field(
                name="⭐ Level Tier",
                value=level_status,
                inline=True,
            )
            
            # Limiting Factor
            if is_balance_limiting:
                limit_msg = (
                    f"🔒 **Your balance tier is limiting your max bet.**\n\n"
                    f"Balance Tier: {format_tier_badge(balance_tier)} → Max Bet: {format_coins(balance_tier.max_bet)}\n"
                    f"Level Tier: {format_tier_badge(level_tier)} → Max Bet: {format_coins(level_tier.max_bet)}"
                )
                if balance_tier.max_balance:
                    limit_msg += f"\n\nReach {format_coins(balance_tier.max_balance)} to unlock higher bets!"
            else:
                limit_msg = (
                    f"🔒 **Your level tier is limiting your max bet.**\n\n"
                    f"Level Tier: {format_tier_badge(level_tier)} → Max Bet: {format_coins(level_tier.max_bet)}\n"
                    f"Balance Tier: {format_tier_badge(balance_tier)} → Max Bet: {format_coins(balance_tier.max_bet)}"
                )
                if level_tier.max_xp:
                    xp_remaining = level_tier.max_xp - user.experience_points
                    limit_msg += f"\n\nGain {xp_remaining:,} more XP to unlock higher bets!"
            
            embed.add_field(
                name="🎲 Effective Max Bet",
                value=limit_msg,
                inline=False,
            )
            
            # How to gain XP
            embed.add_field(
                name="💡 How to Progress",
                value=(
                    "**Gain XP:** Wager in any game (10 coins wagered = 1 XP)\n"
                    "**Increase Balance:** Win games to increase your balance tier\n"
                    "**Hybrid System:** Your max bet is limited by the lower of the two tiers"
                ),
                inline=False,
            )
            
            embed.set_footer(text="Use /balance to view your full stats")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(
        name="tier",
        description="View your tier progression and betting limits"
    )
    async def tier(self, interaction: discord.Interaction) -> None:
        """Display user's tier information and progression."""
        await self._display_tier_info(interaction)
    
    @app_commands.command(
        name="tiers",
        description="View your tier progression and betting limits (alias for /tier)"
    )
    async def tiers(self, interaction: discord.Interaction) -> None:
        """Display user's tier information and progression (alias)."""
        await self._display_tier_info(interaction)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Tier(bot))

