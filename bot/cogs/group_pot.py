"""Group Pot cog - Multi-player high-roll gambling game."""

import asyncio
import json
import logging
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

from database.database import get_session
from database.crud import (
    get_user_by_discord_id,
    get_user_by_id,
    update_user_balance,
    create_game_session,
    get_game_session,
    update_game_status,
    add_duel_participant,
    get_duel_participants,
    update_participant_result,
)
from database.models import GameType, GameStatus, TransactionReason
from utils.helpers import format_coins, get_user_lock

logger = logging.getLogger(__name__)


class GroupPotView(View):
    """View with Join and Start buttons for group pot game."""
    
    def __init__(self, bot: commands.Bot, game_id: int, creator_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.game_id = game_id
        self.creator_id = creator_id
    
    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.primary, emoji="🎲")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        """Handle join button click."""
        async with get_user_lock(interaction.user.id):
            async with get_session() as session:
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                if not user:
                    await interaction.response.send_message(
                        "❌ You are not registered! Use `/register` first.",
                        ephemeral=True,
                    )
                    return
                
                # Get game
                game = await get_game_session(session, self.game_id)
                if not game or game.status != GameStatus.PENDING:
                    await interaction.response.send_message(
                        "❌ This game is no longer available!",
                        ephemeral=True,
                    )
                    return
                
                game_data = json.loads(game.data) if game.data else {}
                amount = game_data.get("amount", 0)
                
                # Check if already joined
                participants = await get_duel_participants(session, game.id)
                if any(p.user_id == user.id for p in participants):
                    await interaction.response.send_message(
                        "❌ You're already in this game!",
                        ephemeral=True,
                    )
                    return
                
                # Add participant
                await add_duel_participant(
                    session,
                    game_id=game.id,
                    user_id=user.id,
                    bet_amount=amount,
                )
                
                await session.commit()
                
                # Get updated participants
                participants = await get_duel_participants(session, game.id)
        
        await interaction.response.send_message(
            f"✅ {interaction.user.display_name} joined the game!",
        )
        
        # Update embed
        async with get_session() as session:
            game = await get_game_session(session, self.game_id)
            if game and game.status == GameStatus.PENDING:
                participants = await get_duel_participants(session, game.id)
                await self._update_message(interaction.message, game, participants)
        
        logger.info(f"User {user.id} joined group pot game {self.game_id}")
    
    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.success, emoji="🚀")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        """Handle start button click (creator only)."""
        async with get_session() as session:
            user = await get_user_by_discord_id(session, interaction.user.id)
            
            if not user:
                await interaction.response.send_message(
                    "❌ You are not registered!",
                    ephemeral=True,
                )
                return
            
            # Check if user is the creator
            game = await get_game_session(session, self.game_id)
            if not game or game.created_by_user_id != user.id:
                await interaction.response.send_message(
                    "❌ Only the game creator can start!",
                    ephemeral=True,
                )
                return
            
            if game.status != GameStatus.PENDING:
                await interaction.response.send_message(
                    "❌ This game is no longer pending!",
                    ephemeral=True,
                )
                return
            
            participants = await get_duel_participants(session, game.id)
            
            # Check minimum participants
            if len(participants) < 2:
                await interaction.response.send_message(
                    "❌ Need at least 2 participants to start the game!",
                    ephemeral=True,
                )
                return
            
            # Set game to ACTIVE
            await update_game_status(session, self.game_id, GameStatus.ACTIVE)
            await session.commit()
        
        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        # Start the rolling animation
        await interaction.response.send_message("🎲 Starting the rolls...")
        
        # Run the game
        cog = self.bot.get_cog("GroupPot")
        if cog:
            await cog._run_group_pot_game(interaction.channel, self.game_id)
    
    async def _update_message(self, message: discord.Message, game, participants):
        """Update the game message embed."""
        game_data = json.loads(game.data) if game.data else {}
        amount = game_data.get("amount", 0)
        
        embed = discord.Embed(
            title="🎲 Group Pot High-Roll Game",
            description=f"**Bet Amount:** {format_coins(amount)}\n"
                       f"**Status:** Waiting for players...",
            color=discord.Color.blue(),
        )
        
        # List participants
        participant_list = []
        for p in participants:
            discord_user = await self.bot.fetch_user(p.user_id)
            is_creator = p.user_id == game.created_by_user_id
            prefix = "👑 " if is_creator else "• "
            participant_list.append(f"{prefix}{discord_user.display_name}")
        
        embed.add_field(
            name=f"Participants ({len(participants)})",
            value="\n".join(participant_list) if participant_list else "None",
            inline=False,
        )
        
        embed.add_field(
            name="How to Play",
            value=(
                "• Click **Join Game** to participate\n"
                "• Creator clicks **Start Game** to begin (min 2 players)\n"
                "• Highest roll wins the difference from lowest roll"
            ),
            inline=False,
        )
        
        embed.set_footer(text="Game ID: " + str(game.id))
        
        try:
            await message.edit(embed=embed)
        except discord.NotFound:
            pass


class GroupPot(commands.Cog):
    """Group pot high-roll game commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def _get_pending_group_pot_in_channel(
        self, session, channel_id: int
    ) -> Optional[tuple]:
        """Get pending GROUP_POT game in channel. Returns (game, participants) or None."""
        from sqlalchemy import select
        from database.models import GameSession
        
        result = await session.execute(
            select(GameSession)
            .where(
                GameSession.type == GameType.GROUP_POT,
                GameSession.status == GameStatus.PENDING,
                GameSession.channel_id == channel_id,
            )
        )
        game = result.scalar_one_or_none()
        
        if not game:
            return None
        
        participants = await get_duel_participants(session, game.id)
        return game, participants
    
    async def _is_user_in_game(self, session, user_id: int, game_id: int) -> bool:
        """Check if user is already in the game."""
        participants = await get_duel_participants(session, game_id)
        return any(p.user_id == user_id for p in participants)
    
    async def _update_game_embed(
        self, message: discord.Message, game, participants, bot
    ) -> None:
        """Update the game message embed with current participants."""
        game_data = json.loads(game.data) if game.data else {}
        amount = game_data.get("amount", 0)
        
        embed = discord.Embed(
            title="🎲 Group Pot High-Roll Game",
            description=f"**Bet Amount:** {format_coins(amount)}\n"
                       f"**Status:** Waiting for players...",
            color=discord.Color.blue(),
        )
        
        # List participants
        participant_list = []
        for p in participants:
            discord_user = await bot.fetch_user(p.user_id)
            is_creator = p.user_id == game.created_by_user_id
            prefix = "👑 " if is_creator else "• "
            participant_list.append(f"{prefix}{discord_user.display_name}")
        
        embed.add_field(
            name=f"Participants ({len(participants)})",
            value="\n".join(participant_list) if participant_list else "None",
            inline=False,
        )
        
        embed.add_field(
            name="How to Play",
            value=(
                "• Click **Join Game** to participate\n"
                "• Creator clicks **Start Game** to begin (min 2 players)\n"
                "• Highest roll wins the difference from lowest roll"
            ),
            inline=False,
        )
        
        embed.set_footer(text="Game ID: " + str(game.id))
        
        try:
            view = GroupPotView(bot, game.id, game.created_by_user_id)
            await message.edit(embed=embed, view=view)
        except discord.NotFound:
            pass
    
    @app_commands.command(
        name="group_start",
        description="Start a group pot high-roll game"
    )
    @app_commands.describe(amount="The bet amount for all participants")
    async def group_start(
        self,
        interaction: discord.Interaction,
        amount: int,
    ) -> None:
        """Create a new group pot game."""
        # Validate amount
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Bet amount must be positive!",
                ephemeral=True,
            )
            return
        
        async with get_user_lock(interaction.user.id):
            async with get_session() as session:
                creator = await get_user_by_discord_id(session, interaction.user.id)
                
                if not creator:
                    await interaction.response.send_message(
                        "❌ You are not registered! Use `/register` first.",
                        ephemeral=True,
                    )
                    return
                
                # Check for existing pending game in channel
                existing = await self._get_pending_group_pot_in_channel(
                    session, interaction.channel_id
                )
                if existing:
                    await interaction.response.send_message(
                        "❌ There's already a pending group pot game in this channel!",
                        ephemeral=True,
                    )
                    return
                
                # Create game session
                game_data = {
                    "amount": amount,
                    "creator_id": creator.id,
                }
                
                game = await create_game_session(
                    session,
                    game_type=GameType.GROUP_POT,
                    creator_user_id=creator.id,
                    channel_id=interaction.channel_id,
                    data=game_data,
                )
                
                # Add creator as first participant
                await add_duel_participant(
                    session,
                    game_id=game.id,
                    user_id=creator.id,
                    bet_amount=amount,
                )
                
                await session.commit()
        
        # Send game announcement with buttons
        embed = discord.Embed(
            title="🎲 Group Pot High-Roll Game",
            description=f"**Bet Amount:** {format_coins(amount)}\n"
                       f"**Status:** Waiting for players...",
            color=discord.Color.blue(),
        )
        
        embed.add_field(
            name=f"Participants (1)",
            value=f"👑 {interaction.user.display_name}",
            inline=False,
        )
        
        embed.add_field(
            name="How to Play",
            value=(
                "• Click **Join Game** to participate\n"
                "• Creator clicks **Start Game** to begin (min 2 players)\n"
                "• Highest roll wins the difference from lowest roll"
            ),
            inline=False,
        )
        
        embed.set_footer(text=f"Game ID: {game.id}")
        
        view = GroupPotView(self.bot, game.id, creator.id)
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        
        # Store message ID for updates
        async with get_session() as session:
            from sqlalchemy import update
            from database.models import GameSession
            await session.execute(
                update(GameSession)
                .where(GameSession.id == game.id)
                .values(message_id=message.id)
            )
            await session.commit()
        
        logger.info(f"Group pot game {game.id} created by user {creator.id}")
    
    
    @app_commands.command(
        name="group_leave",
        description="Leave a pending group pot game"
    )
    async def group_leave(self, interaction: discord.Interaction) -> None:
        """Leave a pending group pot game."""
        async with get_user_lock(interaction.user.id):
            async with get_session() as session:
                user = await get_user_by_discord_id(session, interaction.user.id)
                
                if not user:
                    await interaction.response.send_message(
                        "❌ You are not registered!",
                        ephemeral=True,
                    )
                    return
                
                # Find pending game in channel
                game_info = await self._get_pending_group_pot_in_channel(
                    session, interaction.channel_id
                )
                
                if not game_info:
                    await interaction.response.send_message(
                        "❌ No pending group pot game in this channel!",
                        ephemeral=True,
                    )
                    return
                
                game, participants = game_info
                
                # Check if user is in game
                user_participant = None
                for p in participants:
                    if p.user_id == user.id:
                        user_participant = p
                        break
                
                if not user_participant:
                    await interaction.response.send_message(
                        "❌ You're not in this game!",
                        ephemeral=True,
                    )
                    return
                
                # Remove participant
                await session.delete(user_participant)
                await session.commit()
                
                # Check if game should be cancelled
                remaining_participants = await get_duel_participants(session, game.id)
                
                if len(remaining_participants) == 0:
                    # Cancel game - no one left
                    await update_game_status(session, game.id, GameStatus.CANCELLED)
                    await session.commit()
                    await interaction.response.send_message(
                        f"✅ {interaction.user.display_name} left. Game cancelled (no participants).",
                    )
                    logger.info(f"Group pot game {game.id} cancelled - no participants")
                    return
                
                # If creator left, cancel game
                if user.id == game.created_by_user_id:
                    await update_game_status(session, game.id, GameStatus.CANCELLED)
                    await session.commit()
                    await interaction.response.send_message(
                        f"✅ {interaction.user.display_name} (creator) left. Game cancelled.",
                    )
                    logger.info(f"Group pot game {game.id} cancelled - creator left")
                    return
        
        await interaction.response.send_message(
            f"✅ {interaction.user.display_name} left the game.",
        )
        
        # Update the original message
        async with get_session() as session:
            game_info = await self._get_pending_group_pot_in_channel(
                session, interaction.channel_id
            )
            if game_info:
                game, participants = game_info
                if game.message_id:
                    try:
                        channel = interaction.channel
                        message = await channel.fetch_message(game.message_id)
                        await self._update_game_embed(message, game, participants, self.bot)
                    except discord.NotFound:
                        pass
    
    async def _run_group_pot_game(self, channel: discord.TextChannel, game_id: int) -> None:
        """Run the rolling phase of the group pot game."""
        # Roll for each participant
        async with get_session() as session:
            game = await get_game_session(session, game_id)
            if not game:
                return
            
            participants = await get_duel_participants(session, game_id)
            game_data = json.loads(game.data) if game.data else {}
            amount = game_data.get("amount", 0)
            
            rolls = []
            
            # Show initial embed
            roll_embed = discord.Embed(
                title="🎲 Group Pot High-Roll - Rolling!",
                description=f"**Bet Amount:** {format_coins(amount)}",
                color=discord.Color.blue(),
            )
            
            message = await channel.send(embed=roll_embed)
            
            # Roll for each participant with animation
            for i, participant in enumerate(participants):
                player = await get_user_by_id(session, participant.user_id)
                discord_user = await self.bot.fetch_user(player.discord_id)
                
                # Generate roll
                roll_value = random.randint(1, amount)
                
                # Update participant with roll
                await update_participant_result(
                    session,
                    participant_id=participant.id,
                    result_value=roll_value,
                )
                await session.commit()
                
                rolls.append({
                    "participant": participant,
                    "player": player,
                    "discord_user": discord_user,
                    "roll": roll_value,
                })
                
                # Show roll with dramatic pause
                await asyncio.sleep(1.5)
                
                roll_embed = discord.Embed(
                    title="🎲 Group Pot High-Roll - Rolling!",
                    description=f"**Bet Amount:** {format_coins(amount)}",
                    color=discord.Color.blue(),
                )
                
                for j, r in enumerate(rolls):
                    emoji = "🎲" if j == i else "✅"
                    roll_embed.add_field(
                        name=f"{emoji} {r['discord_user'].display_name}",
                        value=f"**Roll:** {r['roll']:,}",
                        inline=False,
                    )
                
                await message.edit(embed=roll_embed)
            
            # Determine winner and loser
            await asyncio.sleep(2)
            
            # Handle ties
            max_roll = max(r["roll"] for r in rolls)
            min_roll = min(r["roll"] for r in rolls)
            
            winners = [r for r in rolls if r["roll"] == max_roll]
            losers = [r for r in rolls if r["roll"] == min_roll]
            
            # Re-roll ties if needed
            while len(winners) > 1:
                await asyncio.sleep(1)
                tie_embed = discord.Embed(
                    title="🎲 Tie for Winner! Re-rolling...",
                    description=f"Tied players: {', '.join(w['discord_user'].display_name for w in winners)}",
                    color=discord.Color.orange(),
                )
                await message.edit(embed=tie_embed)
                await asyncio.sleep(2)
                
                for w in winners:
                    w["roll"] = random.randint(1, amount)
                
                max_roll = max(w["roll"] for w in winners)
                winners = [w for w in winners if w["roll"] == max_roll]
            
            while len(losers) > 1:
                await asyncio.sleep(1)
                tie_embed = discord.Embed(
                    title="🎲 Tie for Loser! Re-rolling...",
                    description=f"Tied players: {', '.join(l['discord_user'].display_name for l in losers)}",
                    color=discord.Color.orange(),
                )
                await message.edit(embed=tie_embed)
                await asyncio.sleep(2)
                
                for l in losers:
                    l["roll"] = random.randint(1, amount)
                
                min_roll = min(l["roll"] for l in losers)
                losers = [l for l in losers if l["roll"] == min_roll]
            
            winner = winners[0]
            loser = losers[0]
            
            # Calculate transfer amount
            transfer_amount = winner["roll"] - loser["roll"]
            
            # Transfer money from loser to winner
            if transfer_amount > 0:
                async with get_user_lock(winner["player"].id):
                    async with get_user_lock(loser["player"].id):
                        # Deduct from loser
                        await update_user_balance(
                            session,
                            user_id=loser["player"].id,
                            amount=-transfer_amount,
                            reason=TransactionReason.GROUP_POT_LOSS,
                            game_id=game.id,
                        )
                        
                        # Credit to winner
                        await update_user_balance(
                            session,
                            user_id=winner["player"].id,
                            amount=transfer_amount,
                            reason=TransactionReason.GROUP_POT_WIN,
                            game_id=game.id,
                        )
                        
                        # Mark winner
                        await update_participant_result(
                            session,
                            participant_id=winner["participant"].id,
                            is_winner=True,
                        )
                        
                        await session.commit()
            
            # Complete the game
            await update_game_status(session, game.id, GameStatus.COMPLETED)
            await session.commit()
        
        # Show final results
        await asyncio.sleep(1)
        
        final_embed = discord.Embed(
            title="🎲 Group Pot High-Roll - Results!",
            color=discord.Color.gold(),
        )
        
        # Show all rolls
        rolls_sorted = sorted(rolls, key=lambda r: r["roll"], reverse=True)
        roll_text = []
        for r in rolls_sorted:
            emoji = "🏆" if r == winner else ("💀" if r == loser else "•")
            roll_text.append(f"{emoji} **{r['discord_user'].display_name}**: {r['roll']:,}")
        
        final_embed.add_field(
            name="All Rolls",
            value="\n".join(roll_text),
            inline=False,
        )
        
        final_embed.add_field(
            name="🏆 Winner",
            value=f"**{winner['discord_user'].display_name}** rolled **{winner['roll']:,}**",
            inline=True,
        )
        
        final_embed.add_field(
            name="💀 Loser",
            value=f"**{loser['discord_user'].display_name}** rolled **{loser['roll']:,}**",
            inline=True,
        )
        
        final_embed.add_field(
            name="💰 Transfer",
            value=f"**{format_coins(transfer_amount)}** transferred from loser to winner",
            inline=False,
        )
        
        final_embed.set_footer(text=f"Game ID: {game.id}")
        
        await message.edit(embed=final_embed)
        
        logger.info(f"Group pot game {game.id} completed - Winner: {winner['player'].id}, Transfer: {transfer_amount}")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(GroupPot(bot))

