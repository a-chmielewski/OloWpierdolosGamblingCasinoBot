"""Duel cog - 1v1 Deathroll (WoW-style decreasing roll duel)."""

import asyncio
import json
import logging
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import config
from database.database import get_session
from database.crud import (
    get_user_by_discord_id,
    get_user_by_id,
    update_user_balance,
    create_game_session,
    get_game_session,
    get_active_game_for_user,
    get_pending_duel_for_user,
    update_game_status,
    update_game_message_id,
    add_duel_participant,
    get_duel_participants,
    update_participant_result,
)
from database.models import GameType, GameStatus, TransactionReason
from utils.helpers import format_coins, get_user_lock

logger = logging.getLogger(__name__)


class DuelChallengeView(discord.ui.View):
    """View with Accept/Decline buttons for duel challenges."""
    
    def __init__(self, game_id: int, challenger_id: int, opponent_id: int, amount: int):
        super().__init__(timeout=config.DUEL_TIMEOUT_SECONDS)
        self.game_id = game_id
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.amount = amount
        self.response: Optional[bool] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the opponent can use these buttons."""
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message(
                "Only the challenged player can respond to this duel!",
                ephemeral=True,
            )
            return False
        return True
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="⚔️")
    async def accept_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Accept the duel challenge."""
        self.response = True
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="🏃")
    async def decline_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Decline the duel challenge."""
        self.response = False
        self.stop()
        await interaction.response.defer()
    
    async def on_timeout(self) -> None:
        """Handle timeout - challenge expired."""
        self.response = None


class Duel(commands.Cog):
    """Duel commands for 1v1 deathroll gambling."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="duel_start",
        description="Challenge another player to a deathroll duel"
    )
    @app_commands.describe(
        opponent="The player you want to challenge",
        amount="The amount to bet (both players wager this amount)"
    )
    async def duel_start(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
        amount: int,
    ) -> None:
        """Start a deathroll duel challenge."""
        # Validate inputs
        if opponent.bot:
            await interaction.response.send_message(
                "❌ You cannot duel a bot!",
                ephemeral=True,
            )
            return
        
        if opponent.id == interaction.user.id:
            await interaction.response.send_message(
                "❌ You cannot duel yourself!",
                ephemeral=True,
            )
            return
        
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Bet amount must be positive!",
                ephemeral=True,
            )
            return
        
        async with get_session() as session:
            # Check both users are registered
            challenger = await get_user_by_discord_id(session, interaction.user.id)
            if not challenger:
                await interaction.response.send_message(
                    "❌ You are not registered! Use `/register` first.",
                    ephemeral=True,
                )
                return
            
            opponent_user = await get_user_by_discord_id(session, opponent.id)
            if not opponent_user:
                await interaction.response.send_message(
                    f"❌ {opponent.display_name} is not registered! They need to use `/register` first.",
                    ephemeral=True,
                )
                return
            
            # Check balances
            if challenger.balance < amount:
                await interaction.response.send_message(
                    f"❌ Insufficient funds! You have {format_coins(challenger.balance)} but need {format_coins(amount)}.",
                    ephemeral=True,
                )
                return
            
            if opponent_user.balance < amount:
                await interaction.response.send_message(
                    f"❌ {opponent.display_name} doesn't have enough coins! They have {format_coins(opponent_user.balance)}.",
                    ephemeral=True,
                )
                return
            
            # Check for existing active games
            challenger_game = await get_active_game_for_user(session, challenger.id)
            if challenger_game:
                await interaction.response.send_message(
                    "❌ You already have an active game! Finish it first.",
                    ephemeral=True,
                )
                return
            
            opponent_game = await get_active_game_for_user(session, opponent_user.id)
            if opponent_game:
                await interaction.response.send_message(
                    f"❌ {opponent.display_name} is already in an active game!",
                    ephemeral=True,
                )
                return
            
            # Create game session
            game_data = {
                "current_max": amount,
                "challenger_discord_id": interaction.user.id,
                "opponent_discord_id": opponent.id,
            }
            game = await create_game_session(
                session,
                game_type=GameType.DECREASING_DUEL,
                creator_user_id=challenger.id,
                channel_id=interaction.channel_id,
                data=game_data,
            )
            
            # Add participants
            await add_duel_participant(session, game.id, challenger.id, amount)
            await add_duel_participant(session, game.id, opponent_user.id, amount)
            
            game_id = game.id
        
        # Create challenge embed
        embed = discord.Embed(
            title="⚔️ Deathroll Duel Challenge!",
            description=(
                f"**{interaction.user.display_name}** has challenged **{opponent.display_name}** "
                f"to a Deathroll!\n\n"
                f"**Wager:** {format_coins(amount)} each\n"
                f"**Total Pot:** {format_coins(amount * 2)}\n\n"
                f"**Rules:**\n"
                f"• Players take turns rolling from 1 to the previous roll\n"
                f"• First roll is 1-{amount:,}\n"
                f"• Player who rolls **1** loses the pot!\n\n"
                f"{opponent.mention}, do you accept?"
            ),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Challenge expires in {config.DUEL_TIMEOUT_SECONDS} seconds")
        
        # Create view with buttons
        view = DuelChallengeView(
            game_id=game_id,
            challenger_id=interaction.user.id,
            opponent_id=opponent.id,
            amount=amount,
        )
        
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        
        # Store message ID
        async with get_session() as session:
            await update_game_message_id(session, game_id, message.id)
        
        # Wait for response
        await view.wait()
        
        if view.response is True:
            # Accepted - run the duel
            await self._run_duel(interaction.channel, game_id, interaction.user, opponent, amount)
        elif view.response is False:
            # Declined
            embed = discord.Embed(
                title="🏃 Duel Declined",
                description=f"{opponent.display_name} has declined the duel challenge.",
                color=discord.Color.red(),
            )
            await message.edit(embed=embed, view=None)
            
            async with get_session() as session:
                await update_game_status(session, game_id, GameStatus.CANCELLED)
        else:
            # Timeout
            embed = discord.Embed(
                title="⏰ Challenge Expired",
                description="The duel challenge has expired.",
                color=discord.Color.dark_gray(),
            )
            await message.edit(embed=embed, view=None)
            
            async with get_session() as session:
                await update_game_status(session, game_id, GameStatus.CANCELLED)
    
    async def _run_duel(
        self,
        channel: discord.TextChannel,
        game_id: int,
        challenger: discord.Member,
        opponent: discord.Member,
        amount: int,
    ) -> None:
        """Execute the deathroll duel sequence."""
        async with get_session() as session:
            # Verify balances again (in case they changed)
            challenger_user = await get_user_by_discord_id(session, challenger.id)
            opponent_user = await get_user_by_discord_id(session, opponent.id)
            
            if challenger_user.balance < amount or opponent_user.balance < amount:
                embed = discord.Embed(
                    title="❌ Duel Cancelled",
                    description="One of the players no longer has sufficient funds!",
                    color=discord.Color.red(),
                )
                await channel.send(embed=embed)
                await update_game_status(session, game_id, GameStatus.CANCELLED)
                return
            
            # Mark game as active
            await update_game_status(session, game_id, GameStatus.ACTIVE)
            
            # Get participants
            participants = await get_duel_participants(session, game_id)
            challenger_participant = next(p for p in participants if p.user_id == challenger_user.id)
            opponent_participant = next(p for p in participants if p.user_id == opponent_user.id)
        
        # Start the duel
        embed = discord.Embed(
            title="🎲 Deathroll Begins!",
            description=(
                f"**{challenger.display_name}** vs **{opponent.display_name}**\n"
                f"Pot: {format_coins(amount * 2)}\n\n"
                f"Rolling from **1** to **{amount:,}**..."
            ),
            color=discord.Color.purple(),
        )
        await channel.send(embed=embed)
        
        await asyncio.sleep(config.ROLL_DELAY_SECONDS)
        
        # Duel loop
        current_max = amount
        players = [
            (challenger, challenger_user, challenger_participant),
            (opponent, opponent_user, opponent_participant),
        ]
        current_player_idx = 0  # Challenger starts
        
        rolls_log = []
        
        while current_max > 1:
            member, user, participant = players[current_player_idx]
            
            roll = random.randint(1, current_max)
            rolls_log.append((member.display_name, roll, current_max))
            
            if roll == 1:
                # This player loses!
                loser = (member, user, participant)
                winner_idx = 1 - current_player_idx
                winner = players[winner_idx]
                
                # Dramatic reveal for losing roll
                embed = discord.Embed(
                    title="💀 DEATH ROLL!",
                    description=(
                        f"**{member.display_name}** rolled **1** out of {current_max:,}!\n\n"
                        f"☠️ **{member.display_name}** LOSES!"
                    ),
                    color=discord.Color.dark_red(),
                )
                await channel.send(embed=embed)
                
                # Process results
                await self._finalize_duel(
                    channel, game_id, winner, loser, amount, rolls_log
                )
                return
            
            # Normal roll
            roll_emoji = "🎲" if roll > current_max // 2 else "😰"
            embed = discord.Embed(
                description=f"{roll_emoji} **{member.display_name}** rolls **{roll:,}** (1-{current_max:,})",
                color=discord.Color.blue() if current_player_idx == 0 else discord.Color.orange(),
            )
            await channel.send(embed=embed)
            
            current_max = roll
            current_player_idx = 1 - current_player_idx
            
            await asyncio.sleep(config.ROLL_DELAY_SECONDS)
        
        # If current_max is 1, next roll will be 1 (automatic loss)
        member, user, participant = players[current_player_idx]
        loser = (member, user, participant)
        winner_idx = 1 - current_player_idx
        winner = players[winner_idx]
        
        embed = discord.Embed(
            title="💀 FORCED DEATH!",
            description=(
                f"**{member.display_name}** must roll 1 out of 1...\n\n"
                f"☠️ **{member.display_name}** LOSES!"
            ),
            color=discord.Color.dark_red(),
        )
        await channel.send(embed=embed)
        rolls_log.append((member.display_name, 1, 1))
        
        await self._finalize_duel(channel, game_id, winner, loser, amount, rolls_log)
    
    async def _finalize_duel(
        self,
        channel: discord.TextChannel,
        game_id: int,
        winner: tuple,
        loser: tuple,
        amount: int,
        rolls_log: list,
    ) -> None:
        """Finalize the duel - transfer coins and update records."""
        winner_member, winner_user, winner_participant = winner
        loser_member, loser_user, loser_participant = loser
        
        async with get_session() as session:
            # Update balances
            await update_user_balance(
                session,
                user_id=winner_user.id,
                amount=amount,
                reason=TransactionReason.DUEL_WIN,
                game_id=game_id,
            )
            await update_user_balance(
                session,
                user_id=loser_user.id,
                amount=-amount,
                reason=TransactionReason.DUEL_LOSS,
                game_id=game_id,
            )
            
            # Update participant results
            await update_participant_result(
                session,
                participant_id=winner_participant.id,
                is_winner=True,
            )
            await update_participant_result(
                session,
                participant_id=loser_participant.id,
                is_winner=False,
            )
            
            # Mark game as completed
            await update_game_status(session, game_id, GameStatus.COMPLETED)
            
            # Get updated balances
            winner_user = await get_user_by_id(session, winner_user.id)
            loser_user = await get_user_by_id(session, loser_user.id)
        
        # Send victory message
        await asyncio.sleep(config.ROLL_DELAY_SECONDS)
        
        embed = discord.Embed(
            title="🏆 VICTORY!",
            description=(
                f"**{winner_member.display_name}** wins the deathroll!\n\n"
                f"💰 **Winnings:** {format_coins(amount)}\n\n"
                f"**New Balances:**\n"
                f"🥇 {winner_member.display_name}: {format_coins(winner_user.balance)}\n"
                f"💸 {loser_member.display_name}: {format_coins(loser_user.balance)}"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=winner_member.display_avatar.url)
        
        # Add roll history
        rolls_text = "\n".join(
            f"• {name}: {roll:,} / {max_roll:,}"
            for name, roll, max_roll in rolls_log[-10:]  # Last 10 rolls
        )
        if len(rolls_log) > 10:
            rolls_text = f"... ({len(rolls_log) - 10} more rolls)\n" + rolls_text
        
        embed.add_field(name="Roll History", value=rolls_text, inline=False)
        
        await channel.send(embed=embed)
    
    @app_commands.command(
        name="duel_cancel",
        description="Cancel your pending duel challenge"
    )
    async def duel_cancel(self, interaction: discord.Interaction) -> None:
        """Cancel a pending duel that you created."""
        async with get_session() as session:
            user = await get_user_by_discord_id(session, interaction.user.id)
            if not user:
                await interaction.response.send_message(
                    "❌ You are not registered!",
                    ephemeral=True,
                )
                return
            
            game = await get_pending_duel_for_user(session, user.id)
            if not game:
                await interaction.response.send_message(
                    "❌ You don't have any pending duels to cancel.",
                    ephemeral=True,
                )
                return
            
            if game.created_by_user_id != user.id:
                await interaction.response.send_message(
                    "❌ Only the challenger can cancel the duel.",
                    ephemeral=True,
                )
                return
            
            await update_game_status(session, game.id, GameStatus.CANCELLED)
        
        embed = discord.Embed(
            title="🚫 Duel Cancelled",
            description=f"{interaction.user.display_name} has cancelled their duel challenge.",
            color=discord.Color.dark_gray(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Duel(bot))

