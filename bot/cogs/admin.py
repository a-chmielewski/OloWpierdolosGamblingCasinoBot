"""Admin cog - Administrative commands for debugging and management."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.database.database import get_session
from bot.database.crud import (
    get_user_by_discord_id,
    update_user_balance,
    reset_user_balance,
)
from bot.database.models import TransactionReason
from bot.utils.helpers import format_coins, get_user_lock

logger = logging.getLogger(__name__)


def is_admin():
    """Check if user is bot owner or has administrator permission."""
    async def predicate(interaction: discord.Interaction) -> bool:
        # Bot owner always has access
        if interaction.user.id == interaction.client.application.owner.id:
            return True
        
        # Check for administrator permission in guild
        if interaction.guild and interaction.user.guild_permissions.administrator:
            return True
        
        return False
    
    return app_commands.check(predicate)


class Admin(commands.Cog):
    """Administrative commands for managing the casino."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="admin_add_coins",
        description="[ADMIN] Add or remove coins from a user's balance"
    )
    @app_commands.describe(
        user="The user to modify",
        amount="Amount to add (use negative to remove)"
    )
    @is_admin()
    async def admin_add_coins(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int,
    ) -> None:
        """Add or remove coins from a user's balance."""
        async with get_user_lock(user.id):
            async with get_session() as session:
                db_user = await get_user_by_discord_id(session, user.id)
                
                if not db_user:
                    await interaction.response.send_message(
                        f"❌ {user.display_name} is not registered!",
                        ephemeral=True,
                    )
                    return
                
                old_balance = db_user.balance
                
                await update_user_balance(
                    session,
                    user_id=db_user.id,
                    amount=amount,
                    reason=TransactionReason.ADMIN_ADJUSTMENT,
                )
                
                db_user = await get_user_by_discord_id(session, user.id)
                new_balance = db_user.balance
        
        action = "Added" if amount >= 0 else "Removed"
        embed = discord.Embed(
            title="🔧 Admin: Balance Modified",
            description=(
                f"**User:** {user.display_name}\n"
                f"**Action:** {action} {format_coins(abs(amount))}\n"
                f"**Old Balance:** {format_coins(old_balance)}\n"
                f"**New Balance:** {format_coins(new_balance)}"
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"Action by {interaction.user.display_name}")
        
        logger.info(
            f"ADMIN: {interaction.user} ({interaction.user.id}) modified "
            f"{user} ({user.id}) balance by {amount:+d}"
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(
        name="admin_reset_user",
        description="[ADMIN] Reset a user's balance to starting amount"
    )
    @app_commands.describe(user="The user to reset")
    @is_admin()
    async def admin_reset_user(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        """Reset a user's balance to the starting amount."""
        async with get_user_lock(user.id):
            async with get_session() as session:
                db_user = await get_user_by_discord_id(session, user.id)
                
                if not db_user:
                    await interaction.response.send_message(
                        f"❌ {user.display_name} is not registered!",
                        ephemeral=True,
                    )
                    return
                
                old_balance = db_user.balance
                
                await reset_user_balance(session, db_user.id, config.STARTING_BALANCE)
                
                db_user = await get_user_by_discord_id(session, user.id)
                new_balance = db_user.balance
        
        embed = discord.Embed(
            title="🔧 Admin: Balance Reset",
            description=(
                f"**User:** {user.display_name}\n"
                f"**Old Balance:** {format_coins(old_balance)}\n"
                f"**New Balance:** {format_coins(new_balance)}"
            ),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"Action by {interaction.user.display_name}")
        
        logger.info(
            f"ADMIN: {interaction.user} ({interaction.user.id}) reset "
            f"{user} ({user.id}) balance from {old_balance} to {new_balance}"
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(
        name="admin_view_user",
        description="[ADMIN] View detailed user information"
    )
    @app_commands.describe(user="The user to view")
    @is_admin()
    async def admin_view_user(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        """View detailed information about a user."""
        async with get_session() as session:
            db_user = await get_user_by_discord_id(session, user.id)
            
            if not db_user:
                await interaction.response.send_message(
                    f"❌ {user.display_name} is not registered!",
                    ephemeral=True,
                )
                return
        
        embed = discord.Embed(
            title=f"🔧 Admin: User Info - {user.display_name}",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(
            name="IDs",
            value=(
                f"**DB ID:** {db_user.id}\n"
                f"**Discord ID:** {db_user.discord_id}"
            ),
            inline=True,
        )
        
        embed.add_field(
            name="Balance",
            value=(
                f"**Current:** {format_coins(db_user.balance)}\n"
                f"**Earned:** {format_coins(db_user.lifetime_earned)}\n"
                f"**Lost:** {format_coins(db_user.lifetime_lost)}"
            ),
            inline=True,
        )
        
        last_daily = db_user.last_daily.strftime("%Y-%m-%d %H:%M") if db_user.last_daily else "Never"
        embed.add_field(
            name="Timestamps",
            value=(
                f"**Created:** {db_user.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"**Last Daily:** {last_daily}\n"
                f"**Updated:** {db_user.updated_at.strftime('%Y-%m-%d %H:%M')}"
            ),
            inline=False,
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @admin_add_coins.error
    @admin_reset_user.error
    @admin_view_user.error
    async def admin_error_handler(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle admin command errors."""
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ You don't have permission to use admin commands!",
                ephemeral=True,
            )
        else:
            logger.error(f"Admin command error: {error}")
            await interaction.response.send_message(
                f"❌ An error occurred: {error}",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Admin(bot))

