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
    update_last_hourly,
    can_claim_daily,
    can_claim_hourly,
    check_daily_streak_status,
    check_hourly_streak_status,
    update_daily_streak,
    update_hourly_streak,
    calculate_daily_reward,
    calculate_hourly_reward,
    purchase_daily_streak_insurance,
    purchase_hourly_streak_insurance,
)
from database.models import TransactionReason
from utils.helpers import format_coins, get_user_lock
from utils.tier_system import get_balance_tier, get_level_tier, get_max_bet_limit, format_tier_badge

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
                            f"Use `/hourly` to claim your hourly reward.\n"
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
            
            # Get tier information
            balance_tier = get_balance_tier(user.balance)
            level_tier = get_level_tier(user.experience_points)
            max_bet = get_max_bet_limit(user.balance, user.experience_points)
            
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
            
            # Add tier information
            embed.add_field(
                name="🎯 Tier Status",
                value=(
                    f"**Balance Tier:** {format_tier_badge(balance_tier)}\n"
                    f"**Level Tier:** {format_tier_badge(level_tier)} (Lv.{user.level})\n"
                    f"**Max Bet:** {format_coins(max_bet)}\n"
                    f"**XP:** {user.experience_points:,}"
                ),
                inline=False,
            )
            
            embed.set_footer(text="Use /tier for detailed progression info")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            
            await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="daily", description="Claim your daily coin reward")
    async def daily(self, interaction: discord.Interaction) -> None:
        """Claim daily reward with streak bonuses."""
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
                    
                    # Show current streak info when already claimed
                    streak_info = f"\n\n🔥 **Current Streak:** Day {user.daily_streak}"
                    if user.daily_streak_best > 0:
                        streak_info += f"\n🏆 **Best Streak:** Day {user.daily_streak_best}"
                    
                    embed = discord.Embed(
                        title="⏰ Daily Already Claimed",
                        description=(
                            f"You have already claimed your daily reward!\n\n"
                            f"**Time until next claim:** {hours}h {minutes}m {seconds}s"
                            f"{streak_info}"
                        ),
                        color=discord.Color.orange(),
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Check if streak is broken before claiming
                is_broken, missed_periods = await check_daily_streak_status(session, user.id)
                old_streak = user.daily_streak
                
                # Update streak and calculate reward
                new_streak, reward, is_personal_best = await update_daily_streak(session, user.id)
                
                # Grant daily reward with streak bonus
                await update_user_balance(
                    session,
                    user_id=user.id,
                    amount=reward,
                    reason=TransactionReason.DAILY_REWARD,
                )
                await update_last_daily(session, user.id)
                
                # Refresh user data
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                # Build streak fire emoji (more fire for longer streaks)
                fire_count = min(new_streak, 7)
                fire_emoji = "🔥" * fire_count
                
                # Calculate bonus percentage for display
                if new_streak >= config.DAILY_STREAK_MAX_BONUS_DAY:
                    bonus_text = "+100% (MAX)"
                elif new_streak > 1:
                    bonus_pct = int((new_streak - 1) * config.DAILY_STREAK_BONUS_PER_DAY * 100)
                    bonus_text = f"+{bonus_pct}%"
                else:
                    bonus_text = "Base"
                
                # Build description
                description_parts = []
                
                # Streak broken warning
                if is_broken and old_streak > 0:
                    description_parts.append(
                        f"💔 **Streak Reset!** You missed {missed_periods} day(s).\n"
                        f"Previous streak: Day {old_streak}\n"
                    )
                
                # Day 7 special celebration
                if new_streak == config.DAILY_STREAK_MAX_BONUS_DAY:
                    description_parts.append(
                        f"🎉 **BIG DAY 7 BONUS!** 🎉\n"
                    )
                
                description_parts.append(
                    f"{fire_emoji} **Daily Streak: Day {new_streak}!**\n\n"
                    f"You earned {format_coins(reward)} ({bonus_text} streak bonus)\n\n"
                    f"**New Balance:** {format_coins(user.balance)}"
                )
                
                # Personal best notification
                if is_personal_best and new_streak > 1:
                    description_parts.append(
                        f"\n\n🏆 **NEW PERSONAL BEST!** Day {new_streak}!"
                    )
                
                # Tomorrow's preview
                next_reward = calculate_daily_reward(new_streak + 1)
                if next_reward > reward:
                    description_parts.append(
                        f"\n\n📈 Keep the streak! Tomorrow: {format_coins(next_reward)}"
                    )
                
                description_parts.append("\n\nDaily rewards reset at 3 AM Warsaw time!")
                
                # Color based on streak
                if new_streak >= config.DAILY_STREAK_MAX_BONUS_DAY:
                    color = discord.Color.gold()
                elif new_streak >= 4:
                    color = discord.Color.orange()
                else:
                    color = discord.Color.green()
                
                embed = discord.Embed(
                    title="🎁 Daily Reward Claimed!",
                    description="".join(description_parts),
                    color=color,
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                embed.set_footer(text=f"Best streak: Day {user.daily_streak_best}")
                
                await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="hourly", description="Claim your hourly coin reward")
    async def hourly(self, interaction: discord.Interaction) -> None:
        """Claim hourly reward with streak bonuses."""
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
                
                can_claim, time_remaining = await can_claim_hourly(session, user.id)
                
                if not can_claim:
                    minutes, seconds = divmod(int(time_remaining.total_seconds()), 60)
                    
                    # Show current streak info when already claimed
                    streak_info = f"\n\n⏱️ **Current Streak:** {user.hourly_streak} in a row"
                    if user.hourly_streak_best > 0:
                        streak_info += f"\n🏆 **Best Streak:** {user.hourly_streak_best}"
                    streak_info += f"\n\n⚠️ Miss {config.HOURLY_STREAK_MISSED_THRESHOLD} hours and the streak resets."
                    
                    embed = discord.Embed(
                        title="⏰ Hourly Already Claimed",
                        description=(
                            f"You have already claimed your hourly reward!\n\n"
                            f"**Time until next claim:** {minutes}m {seconds}s"
                            f"{streak_info}"
                        ),
                        color=discord.Color.orange(),
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Check if streak is broken before claiming
                is_broken, missed_hours = await check_hourly_streak_status(session, user.id)
                old_streak = user.hourly_streak
                
                # Update streak and calculate reward
                new_streak, reward, is_personal_best = await update_hourly_streak(session, user.id)
                
                # Grant hourly reward with streak bonus
                await update_user_balance(
                    session,
                    user_id=user.id,
                    amount=reward,
                    reason=TransactionReason.HOURLY_REWARD,
                )
                await update_last_hourly(session, user.id)
                
                # Refresh user data
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                # Build streak timer emoji (more timers for longer streaks)
                timer_count = min(new_streak, 5)
                timer_emoji = "⏱️" * timer_count
                
                # Calculate bonus percentage for display
                if new_streak >= config.HOURLY_STREAK_MAX_BONUS_HOUR:
                    bonus_text = "+50% (MAX)"
                elif new_streak > 1:
                    bonus_pct = int((new_streak - 1) * config.HOURLY_STREAK_BONUS_PER_HOUR * 100)
                    bonus_text = f"+{bonus_pct}%"
                else:
                    bonus_text = "Base"
                
                # Build description
                description_parts = []
                
                # Streak broken warning
                if is_broken and old_streak > 0:
                    description_parts.append(
                        f"💔 **Streak Reset!** You missed {missed_hours} hour(s).\n"
                        f"Previous streak: {old_streak} in a row\n\n"
                    )
                
                description_parts.append(
                    f"{timer_emoji} **Hourly Streak: {new_streak} in a row!**\n\n"
                    f"You claimed {format_coins(reward)} ({bonus_text} streak bonus)\n\n"
                    f"**New Balance:** {format_coins(user.balance)}"
                )
                
                # Personal best notification
                if is_personal_best and new_streak > 1:
                    description_parts.append(
                        f"\n\n🏆 **NEW PERSONAL BEST!** {new_streak} hours!"
                    )
                
                # Next hour preview
                next_reward = calculate_hourly_reward(new_streak + 1)
                if next_reward > reward:
                    description_parts.append(
                        f"\n\n📈 Keep it up! Next hour: {format_coins(next_reward)}"
                    )
                
                description_parts.append(
                    f"\n\n⚠️ Miss {config.HOURLY_STREAK_MISSED_THRESHOLD} hours and the streak resets."
                )
                
                # Color based on streak
                if new_streak >= config.HOURLY_STREAK_MAX_BONUS_HOUR:
                    color = discord.Color.gold()
                elif new_streak >= 3:
                    color = discord.Color.blue()
                else:
                    color = discord.Color.teal()
                
                embed = discord.Embed(
                    title="⏱️ Hourly Reward Claimed!",
                    description="".join(description_parts),
                    color=color,
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                embed.set_footer(text=f"Best streak: {user.hourly_streak_best} hours")
                
                await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="streak_save", description="Pay coins to recover a broken streak")
    @app_commands.describe(streak_type="Which streak to save (daily or hourly)")
    @app_commands.choices(streak_type=[
        app_commands.Choice(name="Daily Streak", value="daily"),
        app_commands.Choice(name="Hourly Streak", value="hourly"),
    ])
    async def streak_save(
        self, interaction: discord.Interaction, streak_type: app_commands.Choice[str]
    ) -> None:
        """Purchase streak insurance to recover a broken streak."""
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
                
                if streak_type.value == "daily":
                    is_broken, missed = await check_daily_streak_status(session, user.id)
                    cost = config.DAILY_STREAK_INSURANCE_COST
                    streak_value = user.daily_streak
                    
                    if not is_broken:
                        embed = discord.Embed(
                            title="✅ Streak Not Broken",
                            description=(
                                f"Your daily streak is still intact!\n\n"
                                f"🔥 **Current Streak:** Day {streak_value}\n"
                                f"🏆 **Best Streak:** Day {user.daily_streak_best}\n\n"
                                f"No insurance needed."
                            ),
                            color=discord.Color.green(),
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    
                    if user.balance < cost:
                        embed = discord.Embed(
                            title="❌ Insufficient Funds",
                            description=(
                                f"You need {format_coins(cost)} to save your daily streak.\n\n"
                                f"**Your Balance:** {format_coins(user.balance)}\n"
                                f"**Missing:** {format_coins(cost - user.balance)}"
                            ),
                            color=discord.Color.red(),
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    
                    success, message = await purchase_daily_streak_insurance(session, user.id)
                    
                    if success:
                        user = await get_user_by_discord_id(session, interaction.user.id)
                        embed = discord.Embed(
                            title="🛡️ Daily Streak Saved!",
                            description=(
                                f"Your daily streak has been preserved!\n\n"
                                f"💰 **Cost:** {format_coins(cost)}\n"
                                f"🔥 **Streak Preserved:** Day {streak_value}\n"
                                f"💵 **New Balance:** {format_coins(user.balance)}\n\n"
                                f"Claim your `/daily` now to continue!"
                            ),
                            color=discord.Color.gold(),
                        )
                    else:
                        embed = discord.Embed(
                            title="❌ Insurance Failed",
                            description=message,
                            color=discord.Color.red(),
                        )
                
                else:  # hourly
                    is_broken, missed = await check_hourly_streak_status(session, user.id)
                    cost = config.HOURLY_STREAK_INSURANCE_COST
                    streak_value = user.hourly_streak
                    
                    if not is_broken:
                        embed = discord.Embed(
                            title="✅ Streak Not Broken",
                            description=(
                                f"Your hourly streak is still intact!\n\n"
                                f"⏱️ **Current Streak:** {streak_value} in a row\n"
                                f"🏆 **Best Streak:** {user.hourly_streak_best}\n\n"
                                f"No insurance needed."
                            ),
                            color=discord.Color.green(),
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    
                    if user.balance < cost:
                        embed = discord.Embed(
                            title="❌ Insufficient Funds",
                            description=(
                                f"You need {format_coins(cost)} to save your hourly streak.\n\n"
                                f"**Your Balance:** {format_coins(user.balance)}\n"
                                f"**Missing:** {format_coins(cost - user.balance)}"
                            ),
                            color=discord.Color.red(),
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                    
                    success, message = await purchase_hourly_streak_insurance(session, user.id)
                    
                    if success:
                        user = await get_user_by_discord_id(session, interaction.user.id)
                        embed = discord.Embed(
                            title="🛡️ Hourly Streak Saved!",
                            description=(
                                f"Your hourly streak has been preserved!\n\n"
                                f"💰 **Cost:** {format_coins(cost)}\n"
                                f"⏱️ **Streak Preserved:** {streak_value} in a row\n"
                                f"💵 **New Balance:** {format_coins(user.balance)}\n\n"
                                f"Claim your `/hourly` now to continue!"
                            ),
                            color=discord.Color.gold(),
                        )
                    else:
                        embed = discord.Embed(
                            title="❌ Insurance Failed",
                            description=message,
                            color=discord.Color.red(),
                        )
                
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="streak", description="View your current streak status")
    async def streak(self, interaction: discord.Interaction) -> None:
        """View detailed streak information."""
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
            
            # Check streak statuses
            daily_broken, daily_missed = await check_daily_streak_status(session, user.id)
            hourly_broken, hourly_missed = await check_hourly_streak_status(session, user.id)
            
            # Build daily streak info
            daily_fire = "🔥" * min(user.daily_streak, 7) if user.daily_streak > 0 else "💤"
            daily_status = "💔 BROKEN" if daily_broken else "✅ Active"
            daily_reward = calculate_daily_reward(user.daily_streak + 1 if not daily_broken else 1)
            
            # Build hourly streak info
            hourly_timer = "⏱️" * min(user.hourly_streak, 5) if user.hourly_streak > 0 else "💤"
            hourly_status = "💔 BROKEN" if hourly_broken else "✅ Active"
            hourly_reward = calculate_hourly_reward(user.hourly_streak + 1 if not hourly_broken else 1)
            
            embed = discord.Embed(
                title=f"📊 {interaction.user.display_name}'s Streak Status",
                color=discord.Color.blue(),
            )
            
            # Daily streak section
            daily_section = (
                f"{daily_fire}\n"
                f"**Current:** Day {user.daily_streak}\n"
                f"**Best:** Day {user.daily_streak_best}\n"
                f"**Status:** {daily_status}\n"
                f"**Next Reward:** {format_coins(daily_reward)}"
            )
            if daily_broken and user.daily_streak > 0:
                daily_section += f"\n\n🛡️ Save for {format_coins(config.DAILY_STREAK_INSURANCE_COST)}"
            embed.add_field(name="🔥 Daily Streak", value=daily_section, inline=True)
            
            # Hourly streak section
            hourly_section = (
                f"{hourly_timer}\n"
                f"**Current:** {user.hourly_streak} hours\n"
                f"**Best:** {user.hourly_streak_best} hours\n"
                f"**Status:** {hourly_status}\n"
                f"**Next Reward:** {format_coins(hourly_reward)}"
            )
            if hourly_broken and user.hourly_streak > 0:
                hourly_section += f"\n\n🛡️ Save for {format_coins(config.HOURLY_STREAK_INSURANCE_COST)}"
            embed.add_field(name="⏱️ Hourly Streak", value=hourly_section, inline=True)
            
            # Streak tips
            embed.add_field(
                name="💡 Tips",
                value=(
                    f"• Daily streaks reset if you miss a day\n"
                    f"• Hourly streaks reset after {config.HOURLY_STREAK_MISSED_THRESHOLD} missed hours\n"
                    f"• Use `/streak_save` to recover broken streaks\n"
                    f"• Day 7+ daily = {format_coins(config.DAILY_STREAK_DAY7_REWARD)} max\n"
                    f"• Hour 5+ hourly = {format_coins(config.HOURLY_STREAK_MAX_REWARD)} max"
                ),
                inline=False,
            )
            
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Economy(bot))

