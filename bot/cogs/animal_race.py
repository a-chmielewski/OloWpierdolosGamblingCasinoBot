"""Animal Racing cog - Hilarious multi-player animal racing game."""

import asyncio
import json
import logging
from typing import Optional, List

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
    update_game_status,
    update_game_message_id,
    add_duel_participant,
    get_duel_participants,
    update_participant_result,
    add_user_xp,
)
from database.models import GameType, GameStatus, TransactionReason
from utils.helpers import format_coins, get_user_lock
from utils.race_utils import RaceTrack, format_race_display
from utils.bet_validator import validate_bet
from utils.tier_system import calculate_xp_reward, get_level_tier, format_tier_badge

logger = logging.getLogger(__name__)


class JoinRaceView(discord.ui.View):
    """View with buttons to choose which racer to bet on."""
    
    def __init__(self, game_id: int, bet_amount: int, bot: commands.Bot, guild: discord.Guild, creator_id: int):
        super().__init__(timeout=config.RACE_JOIN_TIMEOUT_SECONDS)
        self.game_id = game_id
        self.bet_amount = bet_amount
        self.bot = bot
        self.creator_id = creator_id
        self.participants_data: dict[int, str] = {}  # user_id -> racer_emoji
        
        # Add button for each racer
        for racer_config in config.RACE_RACERS:
            emoji_str = racer_config["emoji"]
            button_emoji = None
            
            # Handle custom emojis
            if emoji_str.startswith("<:") or emoji_str.startswith("<a:"):
                # Already in proper format: <:name:id> or <a:name:id>
                # Extract emoji ID
                try:
                    emoji_id = int(emoji_str.split(":")[-1].rstrip(">"))
                    emoji_name = emoji_str.split(":")[1]
                    button_emoji = discord.PartialEmoji(name=emoji_name, id=emoji_id)
                except (IndexError, ValueError):
                    button_emoji = None
            elif emoji_str.startswith(":") and emoji_str.endswith(":"):
                # Format like :kubica: - find the emoji in guild
                emoji_name = emoji_str.strip(":")
                guild_emoji = discord.utils.get(guild.emojis, name=emoji_name)
                if guild_emoji:
                    button_emoji = discord.PartialEmoji(name=guild_emoji.name, id=guild_emoji.id)
                else:
                    button_emoji = None
            else:
                # Standard Unicode emoji
                button_emoji = emoji_str
            
            button = discord.ui.Button(
                label=racer_config["name"],
                emoji=button_emoji,
                style=discord.ButtonStyle.primary,
                custom_id=f"bet_{racer_config['name']}",
            )
            button.callback = self._create_button_callback(racer_config["emoji"], guild)
            self.add_item(button)
        
        # Add Start Race button (creator only)
        start_button = discord.ui.Button(
            label="Start Race",
            emoji="🚀",
            style=discord.ButtonStyle.success,
            custom_id="start_race",
            row=1,  # Put on second row
        )
        start_button.callback = self._start_race_callback
        self.add_item(start_button)
    
    async def _start_race_callback(self, interaction: discord.Interaction):
        """Handle start race button click (creator only)."""
        # Check if user is the creator
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ Only the race creator can start the race!",
                ephemeral=True,
            )
            return
        
        # Check if at least one person has joined
        async with get_session() as session:
            game = await get_game_session(session, self.game_id)
            if not game or game.status != GameStatus.PENDING:
                await interaction.response.send_message(
                    "❌ This race has already started or ended!",
                    ephemeral=True,
                )
                return
            
            participants = await get_duel_participants(session, self.game_id)
            
            if len(participants) == 0:
                await interaction.response.send_message(
                    "❌ No one has placed a bet yet! Wait for players to join.",
                    ephemeral=True,
                )
                return
        
        await interaction.response.send_message("🚀 Starting the race early!", ephemeral=False)
        
        # Stop the view to start the race
        self.stop()
    
    def _create_button_callback(self, racer_emoji: str, guild: discord.Guild):
        """Create a callback for a racer button."""
        async def button_callback(interaction: discord.Interaction):
            user_id = interaction.user.id
            
            # Check if already joined
            if user_id in self.participants_data:
                await interaction.response.send_message(
                    f"❌ You've already bet on {self.participants_data[user_id]}!",
                    ephemeral=True,
                )
                return
            
            async with get_session() as session:
                # Check user is registered
                user = await get_user_by_discord_id(session, user_id)
                if not user:
                    await interaction.response.send_message(
                        "❌ You are not registered! Use `/register` first.",
                        ephemeral=True,
                    )
                    return
                
                # Validate bet amount against progressive limits
                is_valid, error_msg = validate_bet(user, self.bet_amount)
                if not is_valid:
                    await interaction.response.send_message(
                        error_msg,
                        ephemeral=True,
                    )
                    return
                
                # Get game and check it's still pending
                game = await get_game_session(session, self.game_id)
                if not game or game.status != GameStatus.PENDING:
                    await interaction.response.send_message(
                        "❌ This race has already started or ended!",
                        ephemeral=True,
                    )
                    return
                
                # Add participant with racer choice stored in game data
                await add_duel_participant(
                    session,
                    game_id=self.game_id,
                    user_id=user.id,
                    bet_amount=self.bet_amount,
                )
                
                # Store racer choice in participants_data
                self.participants_data[user_id] = racer_emoji
                
                # Update game data to include racer choices
                game_data = json.loads(game.data) if game.data else {}
                if "racer_choices" not in game_data:
                    game_data["racer_choices"] = {}
                game_data["racer_choices"][str(user.id)] = racer_emoji
                game.data = json.dumps(game_data)
                await session.flush()
            
            # Find racer name from config
            racer_name = "Unknown"
            for rc in config.RACE_RACERS:
                if rc["emoji"] == racer_emoji:
                    racer_name = rc["name"]
                    break
            
            # Format emoji for display
            display_emoji = racer_emoji
            if racer_emoji.startswith(":") and racer_emoji.endswith(":"):
                # Convert :name: to <:name:id> for display
                emoji_name = racer_emoji.strip(":")
                guild_emoji = discord.utils.get(guild.emojis, name=emoji_name)
                if guild_emoji:
                    display_emoji = str(guild_emoji)
            
            await interaction.response.send_message(
                f"✅ {interaction.user.display_name} bet on {display_emoji} **{racer_name}**!",
                ephemeral=False,
            )
        
        return button_callback


class AnimalRace(commands.Cog):
    """Animal racing game commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="race_start",
        description="Start an animal racing game - bet on silly animals!"
    )
    @app_commands.describe(bet="The amount to bet")
    async def race_start(
        self,
        interaction: discord.Interaction,
        bet: int,
    ) -> None:
        """Start an animal racing game."""
        # Validate bet amount
        if bet < config.RACE_MIN_BET:
            await interaction.response.send_message(
                f"❌ Minimum bet is {format_coins(config.RACE_MIN_BET)}!",
                ephemeral=True,
            )
            return
        
        if bet <= 0:
            await interaction.response.send_message(
                "❌ Bet amount must be positive!",
                ephemeral=True,
            )
            return
        
        async with get_session() as session:
            # Check user is registered
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
            
            # Create game session
            game_data = {
                "bet_amount": bet,
                "creator_discord_id": interaction.user.id,
                "racer_choices": {},
            }
            game = await create_game_session(
                session,
                game_type=GameType.ANIMAL_RACE,
                creator_user_id=user.id,
                channel_id=interaction.channel_id,
                data=game_data,
            )
            
            game_id = game.id
        
        # Create race announcement embed
        embed = discord.Embed(
            title="🏁 Animal Racing - Place Your Bets!",
            description=(
                f"**Bet Amount:** {format_coins(bet)}\n"
                f"**Started by:** {interaction.user.display_name}\n\n"
                f"Choose your racer! Click a button below to place your bet.\n"
                f"Multiple players can bet on the same racer.\n"
                f"Winner takes all! (pot split if multiple winners)"
            ),
            color=discord.Color.blue(),
        )
        
        # Add racer info
        racer_info = []
        for racer_config in config.RACE_RACERS:
            emoji_str = racer_config["emoji"]
            name = racer_config["name"]
            min_speed = racer_config["min_speed"]
            max_speed = racer_config["max_speed"]
            
            # Format emoji for display
            display_emoji = emoji_str
            if emoji_str.startswith(":") and emoji_str.endswith(":"):
                # Convert :name: to <:name:id> for display
                emoji_name = emoji_str.strip(":")
                guild_emoji = discord.utils.get(interaction.guild.emojis, name=emoji_name)
                if guild_emoji:
                    display_emoji = str(guild_emoji)
            
            racer_info.append(f"{display_emoji} **{name}** - Speed: {min_speed}-{max_speed}")
        
        embed.add_field(
            name="Racers",
            value="\n".join(racer_info),
            inline=False,
        )
        
        embed.set_footer(text=f"Race starts in {config.RACE_JOIN_TIMEOUT_SECONDS} seconds or when creator clicks Start Race!")
        
        # Create view with racer selection buttons
        view = JoinRaceView(game_id=game_id, bet_amount=bet, bot=self.bot, guild=interaction.guild, creator_id=interaction.user.id)
        
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        
        # Store message ID
        async with get_session() as session:
            await update_game_message_id(session, game_id, message.id)
        
        # Wait for timeout or max players
        await view.wait()
        
        # Disable all buttons
        for item in view.children:
            item.disabled = True
        
        # Check if anyone joined
        async with get_session() as session:
            game = await get_game_session(session, game_id)
            participants = await get_duel_participants(session, game_id)
            
            if len(participants) == 0:
                # No one joined, cancel game
                embed = discord.Embed(
                    title="❌ Race Cancelled",
                    description="No one placed a bet on this race!",
                    color=discord.Color.dark_gray(),
                )
                await message.edit(embed=embed, view=None)
                await update_game_status(session, game_id, GameStatus.CANCELLED)
                return
        
        # Start the race!
        embed = discord.Embed(
            title="🏁 Race Starting!",
            description=f"{len(participants)} player(s) placed their bets. Let the race begin!",
            color=discord.Color.gold(),
        )
        await message.edit(embed=embed, view=None)
        
        await asyncio.sleep(2)
        await self._run_race(interaction.channel, game_id)
    
    async def _run_race(
        self,
        channel: discord.TextChannel,
        game_id: int,
    ) -> None:
        """Execute the race with animation."""
        # Get guild for emoji lookups
        guild = channel.guild
        
        async with get_session() as session:
            # Mark game as active
            await update_game_status(session, game_id, GameStatus.ACTIVE)
            
            # Get participants and their racer choices
            game = await get_game_session(session, game_id)
            participants = await get_duel_participants(session, game_id)
            game_data = json.loads(game.data) if game.data else {}
            bet_amount = game_data.get("bet_amount", 0)
            racer_choices = game_data.get("racer_choices", {})
            
            # Map user_id to racer_emoji
            user_racer_map = {int(uid): emoji for uid, emoji in racer_choices.items()}
        
        # Initialize race track
        race_track = RaceTrack()
        
        # Create initial race embed
        embed = discord.Embed(
            title="🏁 The Race is ON!",
            description="Watch the racers go!",
            color=discord.Color.gold(),
        )
        
        message = await channel.send(embed=embed)
        await asyncio.sleep(1)
        
        # Race loop
        winner = None
        update_count = 0
        max_updates = 50  # Safety limit
        
        while winner is None and update_count < max_updates:
            # Update all racers
            race_track.update()
            
            # Check for winner
            winner = race_track.check_winner()
            
            # Create progress embed
            embed = discord.Embed(
                title="🏁 Animal Race - In Progress!",
                color=discord.Color.gold(),
            )
            
            # Show each racer's progress
            for racer in race_track.racers:
                # Check if any player bet on this racer
                is_player_bet = any(
                    emoji == racer.emoji for emoji in user_racer_map.values()
                )
                
                # Format emoji for display
                display_emoji = racer.emoji
                if racer.emoji.startswith(":") and racer.emoji.endswith(":"):
                    emoji_name = racer.emoji.strip(":")
                    guild_emoji = discord.utils.get(guild.emojis, name=emoji_name)
                    if guild_emoji:
                        display_emoji = str(guild_emoji)
                
                display_line = format_race_display(
                    racer,
                    race_track.track_length,
                    is_player_bet=is_player_bet,
                    display_emoji=display_emoji,
                )
                
                embed.add_field(
                    name="\u200b",  # Zero-width space for cleaner look
                    value=display_line,
                    inline=False,
                )
            
            embed.set_footer(text=f"First to {config.RACE_TRACK_LENGTH} wins!")
            
            await message.edit(embed=embed)
            
            if winner is None:
                await asyncio.sleep(config.RACE_UPDATE_INTERVAL)
            
            update_count += 1
        
        # Race finished!
        await asyncio.sleep(1)
        
        # Determine winners (players who bet on winning racer)
        async with get_session() as session:
            participants = await get_duel_participants(session, game_id)
            
            winning_participants = []
            losing_participants = []
            
            for participant in participants:
                user_racer_emoji = user_racer_map.get(participant.user_id)
                if user_racer_emoji == winner.emoji:
                    winning_participants.append(participant)
                else:
                    losing_participants.append(participant)
            
            # Calculate pot and payouts
            total_pot = len(participants) * bet_amount
            
            # Calculate XP reward (moved outside if block to be accessible in footer)
            xp_earned = calculate_xp_reward(bet_amount)
            tier_ups = []
            
            if len(winning_participants) > 0:
                # Split pot among winners
                payout_per_winner = total_pot // len(winning_participants)
                profit_per_winner = payout_per_winner - bet_amount
                
                # Update balances for winners
                for participant in winning_participants:
                    await update_user_balance(
                        session,
                        user_id=participant.user_id,
                        amount=profit_per_winner,
                        reason=TransactionReason.ANIMAL_RACE_WIN,
                        game_id=game_id,
                    )
                    
                    # Award XP
                    user, tier_up = await add_user_xp(session, participant.user_id, xp_earned)
                    if tier_up:
                        tier_info = get_level_tier(user.experience_points)
                        member = await channel.guild.fetch_member(user.discord_id)
                        tier_ups.append((member, tier_info))
                    
                    await update_participant_result(
                        session,
                        participant_id=participant.id,
                        is_winner=True,
                    )
                
                # Update balances for losers
                for participant in losing_participants:
                    await update_user_balance(
                        session,
                        user_id=participant.user_id,
                        amount=-bet_amount,
                        reason=TransactionReason.ANIMAL_RACE_LOSS,
                        game_id=game_id,
                    )
                    
                    # Award XP
                    user, tier_up = await add_user_xp(session, participant.user_id, xp_earned)
                    if tier_up:
                        tier_info = get_level_tier(user.experience_points)
                        member = await channel.guild.fetch_member(user.discord_id)
                        tier_ups.append((member, tier_info))
                    
                    await update_participant_result(
                        session,
                        participant_id=participant.id,
                        is_winner=False,
                    )
            else:
                # No winners (shouldn't happen, but handle it)
                for participant in participants:
                    await update_participant_result(
                        session,
                        participant_id=participant.id,
                        is_winner=False,
                    )
            
            # Complete the game
            await update_game_status(session, game_id, GameStatus.COMPLETED)
        
        # Show final results
        # Format winner emoji for display
        winner_display_emoji = winner.emoji
        if winner.emoji.startswith(":") and winner.emoji.endswith(":"):
            emoji_name = winner.emoji.strip(":")
            guild_emoji = discord.utils.get(guild.emojis, name=emoji_name)
            if guild_emoji:
                winner_display_emoji = str(guild_emoji)
        
        final_embed = discord.Embed(
            title=f"🏆 {winner_display_emoji} {winner.name} WINS!",
            description=f"**{winner.name}** crossed the finish line first!",
            color=discord.Color.gold(),
        )
        
        # Show final standings
        standings = race_track.get_standings()
        standings_text = []
        for i, racer in enumerate(standings, 1):
            position_emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "•"
            
            # Format racer emoji for display
            racer_display_emoji = racer.emoji
            if racer.emoji.startswith(":") and racer.emoji.endswith(":"):
                emoji_name = racer.emoji.strip(":")
                guild_emoji = discord.utils.get(guild.emojis, name=emoji_name)
                if guild_emoji:
                    racer_display_emoji = str(guild_emoji)
            
            standings_text.append(f"{position_emoji} {racer_display_emoji} **{racer.name}** - {racer.position} units")
        
        final_embed.add_field(
            name="Final Standings",
            value="\n".join(standings_text),
            inline=False,
        )
        
        # Show winners and payouts
        if len(winning_participants) > 0:
            winners_text = []
            for participant in winning_participants:
                user = await get_user_by_id(session, participant.user_id)
                discord_user = await self.bot.fetch_user(user.discord_id)
                winners_text.append(f"🎉 {discord_user.display_name} won {format_coins(profit_per_winner)}!")
            
            final_embed.add_field(
                name=f"💰 Winners ({len(winning_participants)})",
                value="\n".join(winners_text),
                inline=False,
            )
            
            final_embed.add_field(
                name="Prize Pool",
                value=f"Total pot: {format_coins(total_pot)}\nPayout per winner: {format_coins(payout_per_winner)}",
                inline=False,
            )
        else:
            final_embed.add_field(
                name="😱 No Winners!",
                value="Somehow, no one bet on the winning racer!",
                inline=False,
            )
        
        final_embed.set_footer(text=f"Game ID: {game_id} | +{xp_earned} XP earned per player")
        
        await message.edit(embed=final_embed)
        
        # Send tier-up notifications
        for member, tier_info in tier_ups:
            tier_embed = discord.Embed(
                title="🎉 TIER UP!",
                description=(
                    f"Congratulations {member.mention}!\n\n"
                    f"You've advanced to **{format_tier_badge(tier_info)}**!\n\n"
                    f"**New Max Bet:** {format_coins(tier_info.max_bet)}"
                ),
                color=discord.Color.gold(),
            )
            tier_embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=tier_embed)
        
        logger.info(f"Animal race {game_id} completed - Winner: {winner.name}, {len(winning_participants)} player(s) won")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(AnimalRace(bot))

