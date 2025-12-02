"""Roulette cog - Color-based roulette gambling game."""

import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from database.database import get_session
from database.crud import (
    get_user_by_discord_id,
    update_user_balance,
    add_user_xp,
)
from database.models import TransactionReason
from utils.helpers import format_coins, get_user_lock
from utils.bet_validator import validate_bet
from utils.tier_system import calculate_xp_reward, get_level_tier, format_tier_badge

logger = logging.getLogger(__name__)


class RouletteChoice:
    """Valid roulette color choices."""
    RED = "red"
    BLACK = "black"
    GREEN = "green"


class Roulette(commands.Cog):
    """Roulette gambling game commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Mapping of colors to their numbers on a European roulette wheel
        self.red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        self.black_numbers = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
        self.green_numbers = [0]
    
    def _spin_roulette(self) -> tuple[str, int]:
        """
        Spin the roulette wheel using weighted probabilities.
        
        Returns:
            tuple of (color, number) where color is 'red', 'black', or 'green'
        """
        # Create weighted list: 18 red, 18 black, 1 green
        colors = [RouletteChoice.RED, RouletteChoice.BLACK, RouletteChoice.GREEN]
        weights = [
            config.ROULETTE_RED_CHANCE,
            config.ROULETTE_BLACK_CHANCE,
            config.ROULETTE_GREEN_CHANCE
        ]
        
        outcome_color = random.choices(colors, weights=weights, k=1)[0]
        
        # Select a random number matching the color
        if outcome_color == RouletteChoice.RED:
            outcome_number = random.choice(self.red_numbers)
        elif outcome_color == RouletteChoice.BLACK:
            outcome_number = random.choice(self.black_numbers)
        else:  # GREEN
            outcome_number = random.choice(self.green_numbers)
        
        return outcome_color, outcome_number
    
    def _calculate_payout(self, bet: int, user_choice: str, outcome_color: str) -> tuple[int, bool]:
        """
        Calculate payout based on user's choice and outcome.
        
        Returns:
            tuple of (payout_amount, is_win)
            Positive payout = win, negative = loss
        """
        if user_choice == outcome_color:
            # Win!
            if outcome_color == RouletteChoice.GREEN:
                payout = bet * config.ROULETTE_PAYOUT_GREEN
            else:  # RED or BLACK
                payout = bet * config.ROULETTE_PAYOUT_RED_BLACK
            return payout, True
        else:
            # Loss
            return -bet, False
    
    def _get_color_emoji(self, color: str) -> str:
        """Get emoji representation for a color."""
        if color == RouletteChoice.RED:
            return "🔴"
        elif color == RouletteChoice.BLACK:
            return "⚫"
        else:  # GREEN
            return "🟢"
    
    @app_commands.command(name="roulette", description="Play roulette - bet on red, black, or green")
    @app_commands.describe(
        bet="Amount of coins to bet",
        choice="Color to bet on: red, black, or green"
    )
    @app_commands.choices(choice=[
        app_commands.Choice(name="🔴 Red (18/37 chance, 2x payout)", value=RouletteChoice.RED),
        app_commands.Choice(name="⚫ Black (18/37 chance, 2x payout)", value=RouletteChoice.BLACK),
        app_commands.Choice(name="🟢 Green (1/37 chance, 14x payout)", value=RouletteChoice.GREEN),
    ])
    async def roulette(
        self, 
        interaction: discord.Interaction, 
        bet: int,
        choice: app_commands.Choice[str]
    ) -> None:
        """Play the roulette game."""
        # Validate bet amount
        if bet <= 0:
            await interaction.response.send_message(
                "❌ Bet amount must be positive!",
                ephemeral=True,
            )
            return
        
        # Get user's color choice
        user_choice = choice.value
        
        async with get_user_lock(interaction.user.id):
            async with get_session() as session:
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                if not user:
                    await interaction.response.send_message(
                        "❌ You are not registered! Use `/register` first.",
                        ephemeral=True,
                    )
                    return
                
                # Validate bet amount against progressive limits
                is_valid, error_msg = validate_bet(user, bet)
                if not is_valid:
                    await interaction.response.send_message(
                        error_msg,
                        ephemeral=True,
                    )
                    return
                
                # Spin the roulette wheel
                outcome_color, outcome_number = self._spin_roulette()
                payout, is_win = self._calculate_payout(bet, user_choice, outcome_color)
                
                # Update balance
                reason = TransactionReason.ROULETTE_WIN if is_win else TransactionReason.ROULETTE_LOSS
                await update_user_balance(
                    session,
                    user_id=user.id,
                    amount=payout,
                    reason=reason,
                )
                
                # Award XP for wagering
                xp_earned = calculate_xp_reward(bet)
                user, tier_up = await add_user_xp(session, user.id, xp_earned)
                new_balance = user.balance
                
                # Store tier-up info for notification
                tier_up_info = None
                if tier_up:
                    new_tier = get_level_tier(user.experience_points)
                    tier_up_info = new_tier
        
        # === ANIMATED ROULETTE WHEEL ===
        
        # Step 1: Wheel spinning
        spinning_embed = discord.Embed(
            title="🎡 Roulette Wheel 🎡",
            description="**Spinning the wheel...**",
            color=discord.Color.blue(),
        )
        spinning_embed.add_field(
            name="Your Bet",
            value=f"{self._get_color_emoji(user_choice)} **{user_choice.upper()}** - {format_coins(bet)}",
            inline=False
        )
        spinning_embed.add_field(
            name="Wheel",
            value="🔴 ⚫ 🔴 ⚫ 🟢 🔴 ⚫ 🔴 ⚫",
            inline=False
        )
        spinning_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        spinning_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=spinning_embed)
        message = await interaction.original_response()
        
        # Step 2: Wheel slowing down
        await asyncio.sleep(1.2)
        slowing_embed = discord.Embed(
            title="🎡 Roulette Wheel 🎡",
            description="**The wheel is slowing down...**",
            color=discord.Color.blue(),
        )
        slowing_embed.add_field(
            name="Your Bet",
            value=f"{self._get_color_emoji(user_choice)} **{user_choice.upper()}** - {format_coins(bet)}",
            inline=False
        )
        slowing_embed.add_field(
            name="Wheel",
            value="⚫ 🔴 ⚫ 🟢 🔴 ⚫ 🔴 ⚫ 🔴",
            inline=False
        )
        slowing_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        slowing_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await message.edit(embed=slowing_embed)
        
        # Step 3: Final result
        await asyncio.sleep(1.0)
        
        # Determine embed color based on result
        if is_win:
            if outcome_color == RouletteChoice.GREEN:
                final_color = discord.Color.gold()
            else:
                final_color = discord.Color.green()
        else:
            final_color = discord.Color.red()
        
        final_embed = discord.Embed(
            title="🎡 Roulette Wheel 🎡",
            color=final_color,
        )
        
        # Display result
        outcome_emoji = self._get_color_emoji(outcome_color)
        final_embed.add_field(
            name="Your Bet",
            value=f"{self._get_color_emoji(user_choice)} **{user_choice.upper()}** - {format_coins(bet)}",
            inline=False
        )
        
        final_embed.add_field(
            name="Result",
            value=f"**The ball landed on:**\n{outcome_emoji} **{outcome_color.upper()} {outcome_number}**",
            inline=False,
        )
        
        # Show win/loss
        if is_win:
            if outcome_color == RouletteChoice.GREEN:
                result_text = "🎉 JACKPOT! You hit GREEN!"
            else:
                result_text = f"🎉 Winner! You correctly guessed {outcome_color.upper()}!"
            
            final_embed.add_field(
                name=result_text,
                value=f"**Won:** {format_coins(payout)}\n**Profit:** {format_coins(payout - bet)}",
                inline=False,
            )
        else:
            final_embed.add_field(
                name="😔 Not this time!",
                value=f"**Lost:** {format_coins(abs(payout))}",
                inline=False,
            )
        
        final_embed.add_field(
            name="Balance",
            value=f"**New Balance:** {format_coins(new_balance)}",
            inline=False,
        )
        
        final_embed.set_footer(text=f"Bet: {format_coins(bet)} | +{xp_earned} XP | Odds: {user_choice.capitalize()} pays {config.ROULETTE_PAYOUT_GREEN if user_choice == RouletteChoice.GREEN else config.ROULETTE_PAYOUT_RED_BLACK}x")
        final_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await message.edit(embed=final_embed)
        
        # Send tier-up notification if occurred
        if tier_up_info:
            tier_embed = discord.Embed(
                title="🎉 TIER UP!",
                description=(
                    f"Congratulations {interaction.user.mention}!\n\n"
                    f"You've advanced to **{format_tier_badge(tier_up_info)}**!\n\n"
                    f"**New Max Bet:** {format_coins(tier_up_info.max_bet)}"
                ),
                color=discord.Color.gold(),
            )
            tier_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.channel.send(embed=tier_embed)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Roulette(bot))

