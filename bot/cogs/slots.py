"""Slots cog - Slot machine gambling game."""

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
)
from database.models import TransactionReason
from utils.helpers import format_coins, get_user_lock

logger = logging.getLogger(__name__)


class Slots(commands.Cog):
    """Slots gambling game commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _spin_slots(self) -> list[str]:
        """Generate 3 random slot symbols using weighted selection."""
        return random.choices(
            config.SLOT_SYMBOLS,
            weights=config.SLOT_WEIGHTS,
            k=3
        )
    
    def _calculate_payout(self, symbols: list[str], bet: int) -> tuple[int, str]:
        """
        Calculate payout based on slot symbols.
        
        Returns:
            tuple of (payout_amount, result_description)
            Positive payout = win, negative = loss
        """
        # Check for triple matches
        if symbols[0] == symbols[1] == symbols[2]:
            symbol = symbols[0]
            
            # Death curse - lose double!
            if symbol == "💀":
                return -bet * config.SLOT_PAYOUT_DEATH, "💀 DEATH CURSE! Triple skulls!"
            
            # Jackpot - Diamond
            elif symbol == "💎":
                return bet * config.SLOT_PAYOUT_TRIPLE_JACKPOT, "💎 JACKPOT! Triple diamonds!"
            
            # High tier - Star
            elif symbol == "⭐":
                return bet * config.SLOT_PAYOUT_TRIPLE_HIGH, "⭐ Amazing! Triple stars!"
            
            # Mid tier - Lemon or Cherry
            elif symbol in ["🍋", "🍒"]:
                return bet * config.SLOT_PAYOUT_TRIPLE_MID, f"{symbol} Nice! Triple {symbol}!"
        
        # Check for double matches
        if symbols[0] == symbols[1] or symbols[1] == symbols[2] or symbols[0] == symbols[2]:
            matching_symbol = symbols[0] if symbols[0] == symbols[1] else (
                symbols[1] if symbols[1] == symbols[2] else symbols[0]
            )
            return bet * config.SLOT_PAYOUT_DOUBLE, f"Small win! Two {matching_symbol}"
        
        # No match - loss
        return -bet, "No match. Better luck next time!"
    
    @app_commands.command(name="slots", description="Play the slot machine")
    @app_commands.describe(bet="Amount of coins to bet")
    async def slots(self, interaction: discord.Interaction, bet: int) -> None:
        """Play the slot machine game."""
        # Validate bet amount
        if bet <= 0:
            await interaction.response.send_message(
                "❌ Bet amount must be positive!",
                ephemeral=True,
            )
            return
        
        async with get_user_lock(interaction.user.id):
            async with get_session() as session:
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                if not user:
                    await interaction.response.send_message(
                        "❌ You are not registered! Use `/register` first.",
                        ephemeral=True,
                    )
                    return
                
                # Check balance
                if user.balance < bet:
                    await interaction.response.send_message(
                        f"❌ Insufficient funds! You have {format_coins(user.balance)} but need {format_coins(bet)}.",
                        ephemeral=True,
                    )
                    return
                
                # Spin the slots
                symbols = self._spin_slots()
                payout, result_text = self._calculate_payout(symbols, bet)
                
                # Update balance
                reason = TransactionReason.SLOTS_WIN if payout > 0 else TransactionReason.SLOTS_LOSS
                await update_user_balance(
                    session,
                    user_id=user.id,
                    amount=payout,
                    reason=reason,
                )
                
                # Get updated balance
                user = await get_user_by_discord_id(session, interaction.user.id)
                new_balance = user.balance
        
        # === ANIMATED REEL REVEAL ===
        
        # Step 1: All reels spinning
        spinning_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        spinning_embed.add_field(
            name="Reels",
            value="**🎰 | 🎰 | 🎰**",
            inline=False
        )
        spinning_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        spinning_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=spinning_embed)
        message = await interaction.original_response()
        
        # Step 2: First reel stops
        await asyncio.sleep(0.8)
        reel1_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        reel1_embed.add_field(
            name="Reels",
            value=f"**{symbols[0]} | 🎰 | 🎰**",
            inline=False
        )
        reel1_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        reel1_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await message.edit(embed=reel1_embed)
        
        # Step 3: Second reel stops
        await asyncio.sleep(0.8)
        reel2_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        reel2_embed.add_field(
            name="Reels",
            value=f"**{symbols[0]} | {symbols[1]} | 🎰**",
            inline=False
        )
        reel2_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        reel2_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await message.edit(embed=reel2_embed)
        
        # Step 4: Final reel stops - show result
        await asyncio.sleep(1.0)
        
        # Determine final embed color based on result
        if payout > bet * 5:  # Big win (jackpot or triple high)
            final_color = discord.Color.gold()
        elif payout > 0:
            final_color = discord.Color.green()
        else:
            final_color = discord.Color.red()
        
        final_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            color=final_color,
        )
        
        # Display the final slot machine
        slot_display = f"**🎰 | {symbols[0]} | {symbols[1]} | {symbols[2]} | 🎰**"
        final_embed.add_field(name="Result", value=slot_display, inline=False)
        
        # Show result message
        if payout > 0:
            final_embed.add_field(
                name="🎉 " + result_text,
                value=f"**Won:** {format_coins(payout)}\n**Profit:** {format_coins(payout - bet)}",
                inline=False,
            )
        elif payout < 0:
            final_embed.add_field(
                name="😔 " + result_text,
                value=f"**Lost:** {format_coins(abs(payout))}",
                inline=False,
            )
        else:
            # Edge case: break even (shouldn't happen with current rules)
            final_embed.add_field(name="🤷 " + result_text, value="Break even!", inline=False)
        
        final_embed.add_field(
            name="Balance",
            value=f"**New Balance:** {format_coins(new_balance)}",
            inline=False,
        )
        
        final_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        final_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await message.edit(embed=final_embed)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Slots(bot))

