"""Admin cog - Administrative commands for debugging and management."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from database.database import get_session
from database.crud import (
    get_user_by_discord_id,
    update_user_balance,
    reset_user_balance,
)
from database.models import TransactionReason, User
from utils.helpers import format_coins, get_user_lock

logger = logging.getLogger(__name__)


def is_admin():
    """Check if user is the guild owner."""
    async def predicate(interaction: discord.Interaction) -> bool:
        # Only guild owner has access
        if interaction.guild and interaction.user.id == interaction.guild.owner_id:
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
        
        # Check if target is the server owner
        is_owner = interaction.guild and user.id == interaction.guild.owner_id
        
        if is_owner:
            # Silent/ephemeral message for server owner
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
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            # Public message in Polish for other players
            if amount > 0:
                message = f"Kasyno przyznało pożyczkę biedakowi {user.mention} w wysokości {format_coins(amount)}"
                embed = discord.Embed(
                    description=message,
                    color=discord.Color.gold(),
                )
                
                logger.info(
                    f"ADMIN: {interaction.user} ({interaction.user.id}) gave "
                    f"{user} ({user.id}) {amount} coins"
                )
                
                await interaction.response.send_message(embed=embed)
            else:
                # For removing coins, keep it admin-only
                action = "Removed"
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
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
    
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
    
    @app_commands.command(
        name="reset_casino",
        description="[OWNER ONLY] Reset ALL stats: balance, XP, levels, and optionally game history"
    )
    @app_commands.describe(
        clear_history="Also delete all game and transaction history (default: False)"
    )
    @is_admin()
    async def reset_casino(
        self,
        interaction: discord.Interaction,
        clear_history: bool = False,
    ) -> None:
        """Reset all registered users to starting stats. Guild owner only."""
        # Double check guild owner
        if not interaction.guild or interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(
                "❌ Only the server owner can use this command!",
                ephemeral=True,
            )
            return
        
        # Defer the response as this might take a while
        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            # Get all users from database
            from sqlalchemy import select
            from database.models import Transaction, GameSession, DuelParticipant
            
            result = await session.execute(select(User))
            all_users = result.scalars().all()
            
            if not all_users:
                await interaction.followup.send(
                    "❌ No registered users found!",
                    ephemeral=True,
                )
                return
            
            # Reset all users to starting values
            reset_count = 0
            for db_user in all_users:
                old_balance = db_user.balance
                
                # Reset balance
                db_user.balance = config.STARTING_BALANCE
                db_user.lifetime_earned = config.STARTING_BALANCE
                db_user.lifetime_lost = 0
                
                # Reset progression stats
                db_user.experience_points = 0
                db_user.level = 1
                
                # Reset daily/hourly claims
                db_user.last_daily = None
                db_user.last_hourly = None
                
                reset_count += 1
                logger.info(
                    f"CASINO RESET: User {db_user.name} ({db_user.discord_id}) "
                    f"reset from {old_balance} to {config.STARTING_BALANCE}, XP/Level reset"
                )
            
            await session.flush()
            
            # Optionally clear history
            deleted_transactions = 0
            deleted_games = 0
            deleted_participants = 0
            
            if clear_history:
                # Delete all transactions
                result = await session.execute(select(Transaction))
                transactions = result.scalars().all()
                for transaction in transactions:
                    await session.delete(transaction)
                    deleted_transactions += 1
                
                # Delete all duel participants
                result = await session.execute(select(DuelParticipant))
                participants = result.scalars().all()
                for participant in participants:
                    await session.delete(participant)
                    deleted_participants += 1
                
                # Delete all game sessions
                result = await session.execute(select(GameSession))
                games = result.scalars().all()
                for game in games:
                    await session.delete(game)
                    deleted_games += 1
                
                await session.flush()
            
            await session.commit()
        
        # Send confirmation
        embed = discord.Embed(
            title="🔧 Casino Reset Complete",
            description=(
                f"All registered users have been reset!\n\n"
                f"**Users Reset:** {reset_count}\n"
                f"**Balance Reset:** {format_coins(config.STARTING_BALANCE)}\n"
                f"**XP/Level Reset:** 0 XP / Level 1\n"
                f"**Lifetime Stats:** Cleared"
            ),
            color=discord.Color.gold(),
        )
        
        if clear_history:
            embed.add_field(
                name="📊 History Cleared",
                value=(
                    f"**Transactions Deleted:** {deleted_transactions}\n"
                    f"**Game Sessions Deleted:** {deleted_games}\n"
                    f"**Participants Deleted:** {deleted_participants}"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="📊 History",
                value="Game and transaction history preserved",
                inline=False,
            )
        
        embed.set_footer(text=f"Reset by {interaction.user.display_name}")
        
        logger.warning(
            f"CASINO RESET: {interaction.user} ({interaction.user.id}) "
            f"reset all {reset_count} users (clear_history={clear_history})"
        )
        
        # Send to admin (ephemeral)
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Send public announcement
        if interaction.channel:
            public_embed = discord.Embed(
                title="🎰 CASINO RESET! 🎰",
                description=(
                    f"The casino has been reset by the owner!\n\n"
                    f"🪙 **Balance:** {format_coins(config.STARTING_BALANCE)}\n"
                    f"⭐ **Level:** 1 (0 XP)\n"
                    f"🎯 **Tier:** 🎲 Newcomer\n\n"
                    f"Fresh start for everyone! Good luck gambling! 🎲"
                ),
                color=discord.Color.gold(),
            )
            await interaction.channel.send(embed=public_embed)
    
    @admin_add_coins.error
    @admin_reset_user.error
    @admin_view_user.error
    @reset_casino.error
    async def admin_error_handler(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Handle admin command errors."""
        if isinstance(error, app_commands.CheckFailure):
            message = "❌ Only the server owner can use admin commands!"
        else:
            logger.error(f"Admin command error: {error}")
            message = f"❌ An error occurred: {error}"
        
        # Check if interaction was already responded to
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Admin(bot))

