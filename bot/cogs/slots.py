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
        """Generate 5 random slot symbols using weighted selection."""
        return random.choices(
            config.SLOT_SYMBOLS,
            weights=config.SLOT_WEIGHTS,
            k=5
        )
    
    def _calculate_payout(self, symbols: list[str], bet: int) -> tuple[int, str]:
        """
        Calculate payout based on 5-reel slot symbols.
        
        Returns:
            tuple of (payout_amount, result_description)
            Positive payout = win, negative = loss
        """
        # Count occurrences of each symbol
        symbol_counts = {}
        for symbol in symbols:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        
        max_count = max(symbol_counts.values())
        most_common_symbol = [s for s, count in symbol_counts.items() if count == max_count][0]
        
        # Check for 5 of a kind
        if max_count == 5:
            # Death curse - lose triple!
            if most_common_symbol == "💀":
                return -bet * config.SLOT_PAYOUT_DEATH, "💀💀💀 DEATH CURSE! Five skulls of doom!"
            
            # Mega Jackpot - 5 Diamonds
            elif most_common_symbol == "💎":
                return bet * config.SLOT_PAYOUT_FIVE_JACKPOT, "💎💎💎 7️⃣ 7️⃣ 7️⃣ MEGA JACKPOT! 7️⃣ 7️⃣ 7️⃣ Five diamonds!"
            
            # Big win - 5 Stars
            elif most_common_symbol == "⭐":
                return bet * config.SLOT_PAYOUT_FIVE_HIGH, "⭐⭐⭐ AMAZING! Five stars!"
            
            # Good win - 5 Lemons or Cherries
            elif most_common_symbol in ["🍋", "🍒"]:
                return bet * config.SLOT_PAYOUT_FIVE_MID, f"{most_common_symbol} Excellent! Five {most_common_symbol}!"
        
        # Check for 4 of a kind
        elif max_count == 4:
            return bet * config.SLOT_PAYOUT_FOUR_MATCH, f"Nice! Four {most_common_symbol}"
        
        # Check for 3 of a kind
        elif max_count == 3:
            return bet * config.SLOT_PAYOUT_THREE_MATCH, f"Small win! Three {most_common_symbol}"
        
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
        
        # === ANIMATED REEL REVEAL (5 reels) ===
        
        # Step 1: All reels spinning
        spinning_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        spinning_embed.add_field(
            name="Reels",
            value="**🎰 | 🎰 | 🎰 | 🎰 | 🎰**",
            inline=False
        )
        spinning_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        spinning_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=spinning_embed)
        message = await interaction.original_response()
        
        # Step 2: First reel stops
        await asyncio.sleep(0.6)
        reel1_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        reel1_embed.add_field(
            name="Reels",
            value=f"**{symbols[0]} | 🎰 | 🎰 | 🎰 | 🎰**",
            inline=False
        )
        reel1_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        reel1_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await message.edit(embed=reel1_embed)
        
        # Step 3: Second reel stops
        await asyncio.sleep(0.6)
        reel2_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        reel2_embed.add_field(
            name="Reels",
            value=f"**{symbols[0]} | {symbols[1]} | 🎰 | 🎰 | 🎰**",
            inline=False
        )
        reel2_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        reel2_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await message.edit(embed=reel2_embed)
        
        # Step 4: Third reel stops
        await asyncio.sleep(0.6)
        reel3_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        reel3_embed.add_field(
            name="Reels",
            value=f"**{symbols[0]} | {symbols[1]} | {symbols[2]} | 🎰 | 🎰**",
            inline=False
        )
        reel3_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        reel3_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await message.edit(embed=reel3_embed)
        
        # Step 5: Fourth reel stops
        await asyncio.sleep(0.6)
        reel4_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            description="**Spinning...**",
            color=discord.Color.blue(),
        )
        reel4_embed.add_field(
            name="Reels",
            value=f"**{symbols[0]} | {symbols[1]} | {symbols[2]} | {symbols[3]} | 🎰**",
            inline=False
        )
        reel4_embed.set_footer(text=f"Bet: {format_coins(bet)}")
        reel4_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await message.edit(embed=reel4_embed)
        
        # Step 6: Final reel stops - show result
        await asyncio.sleep(0.8)
        
        # Determine final embed color based on result
        if payout > bet * 100:  # Mega win (777x jackpot)
            final_color = discord.Color.gold()
        elif payout > bet * 5:  # Big win
            final_color = discord.Color.orange()
        elif payout > 0:
            final_color = discord.Color.green()
        else:
            final_color = discord.Color.red()
        
        final_embed = discord.Embed(
            title="🎰 Slot Machine 🎰",
            color=final_color,
        )
        
        # Display the final slot machine (5 reels)
        slot_display = f"**🎰 | {symbols[0]} | {symbols[1]} | {symbols[2]} | {symbols[3]} | {symbols[4]} | 🎰**"
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

