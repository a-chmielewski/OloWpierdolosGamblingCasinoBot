"""Stats cog - User statistics and leaderboards."""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database.database import get_session
from database.crud import (
    get_user_by_discord_id,
    get_richest_users,
    get_user_rank,
    get_user_game_stats,
)
from utils.helpers import format_coins

logger = logging.getLogger(__name__)


class Stats(commands.Cog):
    """Stats and leaderboard commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="stats", description="View your or another player's statistics")
    @app_commands.describe(user="The user to view stats for (leave empty for yourself)")
    async def stats(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ) -> None:
        """Show detailed statistics for a user."""
        target = user or interaction.user
        
        async with get_session() as session:
            db_user = await get_user_by_discord_id(session, target.id)
            
            if not db_user:
                if target == interaction.user:
                    await interaction.response.send_message(
                        "❌ You are not registered! Use `/register` to join the casino.",
                        ephemeral=True,
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ {target.display_name} is not registered!",
                        ephemeral=True,
                    )
                return
            
            # Get rank
            rank = await get_user_rank(session, db_user.id)
            
            # Get game stats
            game_stats = await get_user_game_stats(session, db_user.id)
        
        net_profit = db_user.lifetime_earned - db_user.lifetime_lost
        net_symbol = "+" if net_profit >= 0 else ""
        net_color = discord.Color.green() if net_profit >= 0 else discord.Color.red()
        
        # Calculate win rates
        total_duels = game_stats["duels_played"]
        duel_winrate = (game_stats["duels_won"] / total_duels * 100) if total_duels > 0 else 0
        
        total_slots = game_stats["slots_played"]
        slots_winrate = (game_stats["slots_won"] / total_slots * 100) if total_slots > 0 else 0
        
        total_roulette = game_stats["roulette_played"]
        roulette_winrate = (game_stats["roulette_won"] / total_roulette * 100) if total_roulette > 0 else 0
        
        embed = discord.Embed(
            title=f"📊 {target.display_name}'s Statistics",
            color=net_color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        # Wealth section
        embed.add_field(
            name="💰 Wealth",
            value=(
                f"**Balance:** {format_coins(db_user.balance)}\n"
                f"**Rank:** #{rank}\n"
                f"**Net Profit:** 🪙 {net_symbol}{net_profit:,}"
            ),
            inline=True,
        )
        
        # Lifetime section
        embed.add_field(
            name="📈 Lifetime",
            value=(
                f"**Earned:** {format_coins(db_user.lifetime_earned)}\n"
                f"**Lost:** {format_coins(db_user.lifetime_lost)}"
            ),
            inline=True,
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer
        
        # Duel section
        embed.add_field(
            name="⚔️ Deathroll Duels",
            value=(
                f"**Played:** {game_stats['duels_played']}\n"
                f"**Won:** {game_stats['duels_won']}\n"
                f"**Lost:** {game_stats['duels_lost']}\n"
                f"**Win Rate:** {duel_winrate:.1f}%"
            ),
            inline=True,
        )
        
        # Slots section
        embed.add_field(
            name="🎰 Slot Machine",
            value=(
                f"**Played:** {game_stats['slots_played']}\n"
                f"**Won:** {game_stats['slots_won']}\n"
                f"**Lost:** {game_stats['slots_lost']}\n"
                f"**Win Rate:** {slots_winrate:.1f}%"
            ),
            inline=True,
        )
        
        # Roulette section
        embed.add_field(
            name="🎡 Roulette",
            value=(
                f"**Played:** {game_stats['roulette_played']}\n"
                f"**Won:** {game_stats['roulette_won']}\n"
                f"**Lost:** {game_stats['roulette_lost']}\n"
                f"**Win Rate:** {roulette_winrate:.1f}%"
            ),
            inline=True,
        )
        
        # Records section
        biggest_win = game_stats["biggest_win"]
        biggest_loss = game_stats["biggest_loss"]
        embed.add_field(
            name="🏆 Records",
            value=(
                f"**Biggest Win:** {format_coins(biggest_win) if biggest_win else 'N/A'}\n"
                f"**Biggest Loss:** {format_coins(biggest_loss) if biggest_loss else 'N/A'}"
            ),
            inline=True,
        )
        
        # Footer with account age
        embed.set_footer(text=f"Account created: {db_user.created_at.strftime('%Y-%m-%d')}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="leaderboard", description="View the richest players in the casino")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """Show the top 10 richest users."""
        async with get_session() as session:
            top_users = await get_richest_users(session, limit=10)
            
            if not top_users:
                await interaction.response.send_message(
                    "No players registered yet! Be the first with `/register`.",
                    ephemeral=True,
                )
                return
            
            # Get requesting user's rank if registered
            requester = await get_user_by_discord_id(session, interaction.user.id)
            requester_rank = None
            if requester:
                requester_rank = await get_user_rank(session, requester.id)
        
        embed = discord.Embed(
            title="🏆 Casino Leaderboard",
            description="The richest gamblers in Olo Wpierdolo's Casino",
            color=discord.Color.gold(),
        )
        
        # Medal emojis for top 3
        medals = ["🥇", "🥈", "🥉"]
        
        leaderboard_text = []
        for i, user in enumerate(top_users):
            rank_display = medals[i] if i < 3 else f"**#{i + 1}**"
            net_profit = user.lifetime_earned - user.lifetime_lost
            net_symbol = "+" if net_profit >= 0 else ""
            
            # Try to get Discord user for display name
            discord_user = interaction.guild.get_member(user.discord_id)
            display_name = discord_user.display_name if discord_user else user.name
            
            leaderboard_text.append(
                f"{rank_display} **{display_name}**\n"
                f"   └ {format_coins(user.balance)} (Net: {net_symbol}{net_profit:,})"
            )
        
        embed.add_field(
            name="Top 10 Richest",
            value="\n".join(leaderboard_text) or "No data",
            inline=False,
        )
        
        # Show requester's rank if not in top 10
        if requester and requester_rank and requester_rank > 10:
            embed.add_field(
                name="Your Position",
                value=(
                    f"**#{requester_rank}** - {format_coins(requester.balance)}"
                ),
                inline=False,
            )
        
        embed.set_footer(text="Use /stats to view detailed statistics")
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Stats(bot))

