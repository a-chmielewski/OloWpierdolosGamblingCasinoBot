"""Roulette cog - Color-based roulette gambling game."""

import asyncio
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
    add_user_xp,
    create_game_session,
    get_game_session,
    get_active_game_for_user,
    update_game_status,
    update_game_message_id,
    add_duel_participant,
    get_duel_participants,
    update_participant_result,
)
from database.models import GameType, GameStatus, TransactionReason
from utils.helpers import format_coins, get_user_lock
from utils.bet_validator import validate_bet
from utils.tier_system import calculate_xp_reward, get_level_tier, format_tier_badge

logger = logging.getLogger(__name__)


class RouletteChoice:
    """Valid roulette color choices."""
    RED = "red"
    BLACK = "black"
    GREEN = "green"


class BetType:
    """Valid roulette bet types."""
    COLOR = "color"
    ODD_EVEN = "odd_even"
    HIGH_LOW = "high_low"


class OddEvenChoice:
    """Valid odd/even choices."""
    ODD = "odd"
    EVEN = "even"


class HighLowChoice:
    """Valid high/low choices."""
    HIGH = "high"  # 1-18
    LOW = "low"    # 19-36


class GameModeView(discord.ui.View):
    """View with buttons to choose Solo or Multiplayer mode."""
    
    def __init__(self, game_id: int, creator_id: int):
        super().__init__(timeout=10)
        self.game_id = game_id
        self.creator_id = creator_id
        self.mode: Optional[str] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the creator can choose the mode."""
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "Only the game creator can choose the mode!",
                ephemeral=True,
            )
            return False
        return True
    
    @discord.ui.button(label="Play Solo", style=discord.ButtonStyle.primary, emoji="🎴")
    async def solo_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Start solo game immediately."""
        self.mode = "solo"
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="Wait for Players", style=discord.ButtonStyle.success, emoji="👥")
    async def multiplayer_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Wait for other players to join."""
        self.mode = "multiplayer"
        self.stop()
        await interaction.response.defer()


class JoinGameView(discord.ui.View):
    """View with button to join a pending roulette game."""
    
    def __init__(self, game_id: int, bet_amount: int, existing_player_ids: list[int], creator_id: int):


        super().__init__(timeout=config.ROULETTE_JOIN_TIMEOUT_SECONDS)
        self.game_id = game_id
        self.bet_amount = bet_amount
        self.existing_player_ids = existing_player_ids
        self.new_players: list[int] = []
        self.creator_id = creator_id
        self.early_start = False
    
    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="🃏")
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Join the roulette game."""
        user_id = interaction.user.id
        
        # Check if already joined
        if user_id in self.existing_player_ids or user_id in self.new_players:
            await interaction.response.send_message(
                "You have already joined this game!",
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
            
            # Check for active game
            active_game = await get_active_game_for_user(session, user.id)
            if active_game:
                await interaction.response.send_message(
                    "❌ You already have an active game! Finish it first.",
                    ephemeral=True,
                )
                return
            
            # Add participant
            await add_duel_participant(session, self.game_id, user.id, self.bet_amount)
            self.new_players.append(user_id)
        
        await interaction.response.send_message(
            f"✅ {interaction.user.display_name} joined the game!",
            ephemeral=False,
        )
    
    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, emoji="🎮")
    async def start_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Start the game early (creator only)."""
        # Check if user is the creator
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "Only the game creator can start the game early!",
                ephemeral=True,
            )
            return
        
        self.early_start = True
        self.stop()
        await interaction.response.send_message(
            f"🎮 {interaction.user.display_name} started the game!",
            ephemeral=False,
        )


class BetTypeSelectionView(discord.ui.View):
    """View for player to select their bet type (first stage)."""
    
    def __init__(self, player_id: int):
        super().__init__(timeout=30)
        self.player_id = player_id
        self.selected_type: Optional[str] = None
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the specific player can choose their bet type."""
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "This is not your bet selection!",
                ephemeral=True,
            )
            return False
        return True
    
    @discord.ui.button(label="Color Bet", style=discord.ButtonStyle.primary, emoji="🎨")
    async def color_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Select color bet type."""
        self.selected_type = BetType.COLOR
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="Odd/Even Bet", style=discord.ButtonStyle.secondary, emoji="🔢")
    async def odd_even_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Select odd/even bet type."""
        self.selected_type = BetType.ODD_EVEN
        self.stop()
        await interaction.response.defer()
    
    @discord.ui.button(label="High/Low Bet", style=discord.ButtonStyle.success, emoji="📊")
    async def high_low_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Select high/low bet type."""
        self.selected_type = BetType.HIGH_LOW
        self.stop()
        await interaction.response.defer()


class BetValueSelectionView(discord.ui.View):
    """View for player to select their specific bet value (second stage)."""
    
    def __init__(self, player_id: int, bet_type: str):
        super().__init__(timeout=30)
        self.player_id = player_id
        self.bet_type = bet_type
        self.selected_value: Optional[str] = None
        
        # Remove all buttons first
        self.clear_items()
        
        # Add appropriate buttons based on bet type
        if bet_type == BetType.COLOR:
            self.add_item(self._create_button("Red", discord.ButtonStyle.danger, "🔴", RouletteChoice.RED))
            self.add_item(self._create_button("Black", discord.ButtonStyle.secondary, "⚫", RouletteChoice.BLACK))
            self.add_item(self._create_button("Green", discord.ButtonStyle.success, "🟢", RouletteChoice.GREEN))
        elif bet_type == BetType.ODD_EVEN:
            self.add_item(self._create_button("Odd", discord.ButtonStyle.primary, "1️⃣", OddEvenChoice.ODD))
            self.add_item(self._create_button("Even", discord.ButtonStyle.primary, "2️⃣", OddEvenChoice.EVEN))
        elif bet_type == BetType.HIGH_LOW:
            self.add_item(self._create_button("High (19-36)", discord.ButtonStyle.success, "⬆️", HighLowChoice.HIGH))
            self.add_item(self._create_button("Low (1-18)", discord.ButtonStyle.danger, "⬇️", HighLowChoice.LOW))
    
    def _create_button(self, label: str, style: discord.ButtonStyle, emoji: str, value: str):
        """Create a button with callback."""
        button = discord.ui.Button(label=label, style=style, emoji=emoji)
        
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player_id:
                await interaction.response.send_message(
                    "This is not your bet selection!",
                    ephemeral=True,
                )
                return
            
            self.selected_value = value
            self.stop()
            
            # Format display message based on bet type
            if self.bet_type == BetType.COLOR:
                emoji_map = {RouletteChoice.RED: "🔴", RouletteChoice.BLACK: "⚫", RouletteChoice.GREEN: "🟢"}
                await interaction.response.send_message(
                    f"{emoji_map[value]} {interaction.user.display_name} bet on **{value.upper()}**!",
                    ephemeral=False,
                )
            elif self.bet_type == BetType.ODD_EVEN:
                await interaction.response.send_message(
                    f"{'1️⃣' if value == OddEvenChoice.ODD else '2️⃣'} {interaction.user.display_name} bet on **{value.upper()}**!",
                    ephemeral=False,
                )
            elif self.bet_type == BetType.HIGH_LOW:
                range_text = "19-36" if value == HighLowChoice.HIGH else "1-18"
                await interaction.response.send_message(
                    f"{'⬆️' if value == HighLowChoice.HIGH else '⬇️'} {interaction.user.display_name} bet on **{value.upper()} ({range_text})**!",
                    ephemeral=False,
                )
        
        button.callback = callback
        return button
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the specific player can choose their bet value."""
        if interaction.user.id != self.player_id:
            await interaction.response.send_message(
                "This is not your bet selection!",
                ephemeral=True,
            )
            return False
        return True


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
    
    def _calculate_payout(
        self, 
        bet: int, 
        bet_type: str, 
        user_choice: str, 
        outcome_number: int, 
        outcome_color: str
    ) -> tuple[int, bool]:
        """
        Calculate payout based on user's choice and outcome.
        
        Args:
            bet: Bet amount
            bet_type: Type of bet (color, odd_even, high_low)
            user_choice: User's specific choice
            outcome_number: The number that came up (0-36)
            outcome_color: The color that came up
            
        Returns:
            tuple of (payout_amount, is_win)
            Positive payout = win, negative = loss
        """
        if bet_type == BetType.COLOR:
            # Color bet - check color match
            if user_choice == outcome_color:
                if outcome_color == RouletteChoice.GREEN:
                    payout = bet * config.ROULETTE_PAYOUT_GREEN
                else:  # RED or BLACK
                    payout = bet * config.ROULETTE_PAYOUT_RED_BLACK
                return payout, True
            else:
                return -bet, False
        
        elif bet_type == BetType.ODD_EVEN:
            # Odd/Even bet - 0 loses, check if 1-36 matches odd/even
            if outcome_number == 0:
                return -bet, False
            
            is_odd = outcome_number % 2 == 1
            
            if (user_choice == OddEvenChoice.ODD and is_odd) or \
               (user_choice == OddEvenChoice.EVEN and not is_odd):
                payout = bet * config.ROULETTE_PAYOUT_RED_BLACK  # 2x payout
                return payout, True
            else:
                return -bet, False
        
        elif bet_type == BetType.HIGH_LOW:
            # High/Low bet - 0 loses, check if number in range
            if outcome_number == 0:
                return -bet, False
            
            is_low = 1 <= outcome_number <= 18
            is_high = 19 <= outcome_number <= 36
            
            if (user_choice == HighLowChoice.LOW and is_low) or \
               (user_choice == HighLowChoice.HIGH and is_high):
                payout = bet * config.ROULETTE_PAYOUT_RED_BLACK  # 2x payout
                return payout, True
            else:
                return -bet, False
        
        # Default case - shouldn't reach here
        return -bet, False
    
    def _get_color_emoji(self, color: str) -> str:
        """Get emoji representation for a color."""
        if color == RouletteChoice.RED:
            return "🔴"
        elif color == RouletteChoice.BLACK:
            return "⚫"
        else:  # GREEN
            return "🟢"
    
    def _create_roulette_board(self, winning_number: int) -> str:
        """
        Create ASCII representation of roulette wheel with winning number highlighted.
        
        Args:
            winning_number: The number that won (0-36)
            
        Returns:
            Formatted string with the roulette board
        """
        # European roulette wheel order
        wheel_order = [
            0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30,
            8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
        ]
        
        # Create board display - show numbers with colors
        board_lines = ["🎡 **ROULETTE WHEEL** 🎡", "```"]
        
        # Display in rows of 6 numbers
        for i in range(0, len(wheel_order), 6):
            row_numbers = wheel_order[i:i+6]
            row_display = []
            
            for num in row_numbers:
                # Determine color
                if num == 0:
                    color_emoji = "🟢"
                elif num in self.red_numbers:
                    color_emoji = "🔴"
                else:
                    color_emoji = "⚫"
                
                # Highlight winning number
                if num == winning_number:
                    row_display.append(f"➡️{num:2d}{color_emoji}")
                else:
                    row_display.append(f" {num:2d}{color_emoji}")
            
            board_lines.append(" ".join(row_display))
        
        board_lines.append("```")
        return "\n".join(board_lines)
    
    def _check_near_miss(
        self, 
        bet_type: str, 
        user_choice: str, 
        outcome_number: int, 
        outcome_color: str
    ) -> Optional[str]:
        """
        Check if the result was a near-miss and return dramatic message.
        
        Args:
            bet_type: Type of bet
            user_choice: User's choice
            outcome_number: Winning number
            outcome_color: Winning color
            
        Returns:
            Message string if near-miss, None otherwise
        """
        # European wheel order for adjacency
        wheel_order = [
            0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30,
            8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
        ]
        
        try:
            outcome_idx = wheel_order.index(outcome_number)
        except ValueError:
            return None
        
        # Get adjacent numbers on wheel
        left_idx = (outcome_idx - 1) % len(wheel_order)
        right_idx = (outcome_idx + 1) % len(wheel_order)
        adjacent_numbers = [wheel_order[left_idx], wheel_order[right_idx]]
        
        if bet_type == BetType.COLOR:
            # Check if adjacent numbers match user's color choice
            for adj_num in adjacent_numbers:
                if adj_num == 0 and user_choice == RouletteChoice.GREEN:
                    return f"😱 **SO CLOSE!** The ball almost landed on **GREEN 0**!"
                elif adj_num in self.red_numbers and user_choice == RouletteChoice.RED:
                    return f"😱 **SO CLOSE!** The ball was right next to **RED {adj_num}**!"
                elif adj_num in self.black_numbers and user_choice == RouletteChoice.BLACK:
                    return f"😱 **SO CLOSE!** The ball was right next to **BLACK {adj_num}**!"
        
        elif bet_type == BetType.ODD_EVEN:
            # Check if adjacent numbers match user's odd/even choice
            for adj_num in adjacent_numbers:
                if adj_num == 0:
                    continue
                is_adj_odd = adj_num % 2 == 1
                if (user_choice == OddEvenChoice.ODD and is_adj_odd) or \
                   (user_choice == OddEvenChoice.EVEN and not is_adj_odd):
                    return f"😱 **SO CLOSE!** The ball almost hit **{adj_num} ({user_choice.upper()})**!"
        
        elif bet_type == BetType.HIGH_LOW:
            # Check if adjacent numbers match user's high/low choice
            for adj_num in adjacent_numbers:
                if adj_num == 0:
                    continue
                is_low = 1 <= adj_num <= 18
                is_high = 19 <= adj_num <= 36
                
                if (user_choice == HighLowChoice.LOW and is_low) or \
                   (user_choice == HighLowChoice.HIGH and is_high):
                    range_text = "1-18" if is_low else "19-36"
                    return f"😱 **SO CLOSE!** The ball almost hit **{adj_num} ({range_text})**!"
        
        return None
    
    def _get_dealer_call(self, call_type: str) -> str:
        """
        Get a random dealer call for casino atmosphere.
        
        Args:
            call_type: Type of call - 'opening', 'spinning', 'win', 'loss'
            
        Returns:
            Random dealer call string
        """
        if call_type == "opening":
            return random.choice(config.ROULETTE_DEALER_CALLS_OPENING)
        elif call_type == "spinning":
            return random.choice(config.ROULETTE_DEALER_CALLS_SPINNING)
        elif call_type == "win":
            return random.choice(config.ROULETTE_DEALER_CALLS_CLOSING_WIN)
        elif call_type == "loss":
            return random.choice(config.ROULETTE_DEALER_CALLS_CLOSING_LOSS)
        return ""
    
    @app_commands.command(name="roulette", description="Play roulette - bet on red, black, or green (solo or multiplayer)")
    @app_commands.describe(bet="Amount of coins to bet")
    async def roulette(
        self, 
        interaction: discord.Interaction, 
        bet: int
    ) -> None:
        """Start a roulette game."""
        # Validate bet amount
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
            
            # Check for existing active game
            active_game = await get_active_game_for_user(session, user.id)
            if active_game:
                await interaction.response.send_message(
                    "❌ You already have an active game! Finish it first.",
                    ephemeral=True,
                )
                return
            
            # Create game session
            game_data = {
                "bet_amount": bet,
                "creator_discord_id": interaction.user.id,
            }
            game = await create_game_session(
                session,
                game_type=GameType.ROULETTE,
                creator_user_id=user.id,
                channel_id=interaction.channel_id,
                data=game_data,
            )
            
            # Add creator as first participant
            await add_duel_participant(session, game.id, user.id, bet)
            
            game_id = game.id
        
        # Create mode selection embed
        embed = discord.Embed(
            title="🎡 Roulette Game",
            description=(
                f"**{interaction.user.display_name}** wants to play Roulette!\n\n"
                f"**Bet Amount:** {format_coins(bet)}\n\n"
                f"Choose your game mode:"
            ),
            color=discord.Color.blue(),
        )
        
        # Create view with mode selection buttons
        view = GameModeView(game_id=game_id, creator_id=interaction.user.id)
        
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        
        # Store message ID
        async with get_session() as session:
            await update_game_message_id(session, game_id, message.id)
        
        # Wait for mode selection
        await view.wait()
        
        if view.mode == "solo":
            # Start solo game - player needs to select color
            embed = discord.Embed(
                title="🎴 Solo Roulette",
                description=f"{interaction.user.display_name} is playing solo!",
                color=discord.Color.purple(),
            )
            await message.edit(embed=embed, view=None)
            await self._run_solo_game(interaction.channel, game_id, interaction.user.id, bet)
        
        elif view.mode == "multiplayer":
            # Wait for players to join
            embed = discord.Embed(
                title="👥 Multiplayer Roulette - Waiting for Players",
                description=(
                    f"**Bet Amount:** {format_coins(bet)}\n"
                    f"**Creator:** {interaction.user.display_name}\n\n"
                    f"Other players can join by clicking the button below!\n"
                    f"Game starts in {config.ROULETTE_JOIN_TIMEOUT_SECONDS} seconds or when creator clicks Start Game."
                ),
                color=discord.Color.gold(),
            )
            
            join_view = JoinGameView(
                game_id=game_id,
                bet_amount=bet,
                existing_player_ids=[interaction.user.id],
                creator_id=interaction.user.id,
            )
            
            await message.edit(embed=embed, view=join_view)
            await join_view.wait()
            
            # Get all participants
            player_ids = [interaction.user.id] + join_view.new_players
            
            if len(player_ids) == 1:
                embed = discord.Embed(
                    title="🎴 Starting Solo Game",
                    description="No other players joined. Starting solo game!",
                    color=discord.Color.blue(),
                )
            else:
                embed = discord.Embed(
                    title="🎡 Starting Multiplayer Game",
                    description=f"{len(player_ids)} players joined! Let's play!",
                    color=discord.Color.green(),
                )
            
            await message.edit(embed=embed, view=None)
            await self._run_multiplayer_game(interaction.channel, game_id, player_ids, bet)
        
        else:
            # Timeout - cancel game
            embed = discord.Embed(
                title="⏰ Game Cancelled",
                description="Mode selection timed out.",
                color=discord.Color.dark_gray(),
            )
            await message.edit(embed=embed, view=None)
            
            async with get_session() as session:
                await update_game_status(session, game_id, GameStatus.CANCELLED)


    async def _run_solo_game(
        self,
        channel: discord.TextChannel,
        game_id: int,
        player_id: int,
        bet: int,
    ) -> None:
        """Execute solo roulette game with enhanced animations and features."""
        member = await channel.guild.fetch_member(player_id)
        
        # === STAGE 1: BET TYPE SELECTION ===
        type_embed = discord.Embed(
            title="🎰 Choose Your Bet Type",
            description=f"{member.display_name}, what type of bet do you want to make?",
            color=discord.Color.blue(),
        )
        type_view = BetTypeSelectionView(player_id=player_id)
        
        type_message = await channel.send(embed=type_embed, view=type_view)
        await type_view.wait()
        
        if not type_view.selected_type:
            # Timeout - default to color bet
            bet_type = BetType.COLOR
            await channel.send(f"⏰ {member.display_name} timed out. Defaulting to **COLOR BET**.")
        else:
            bet_type = type_view.selected_type
        
        await asyncio.sleep(0.3)
        
        # === STAGE 2: BET VALUE SELECTION ===
        value_embed = discord.Embed(
            title="🎯 Choose Your Bet",
            description=f"{member.display_name}, make your choice!",
            color=discord.Color.green(),
        )
        value_view = BetValueSelectionView(player_id=player_id, bet_type=bet_type)
        
        value_message = await channel.send(embed=value_embed, view=value_view)
        await value_view.wait()
        
        if not value_view.selected_value:
            # Timeout - default based on bet type
            if bet_type == BetType.COLOR:
                user_choice = RouletteChoice.RED
            elif bet_type == BetType.ODD_EVEN:
                user_choice = OddEvenChoice.ODD
            else:
                user_choice = HighLowChoice.HIGH
            await channel.send(f"⏰ {member.display_name} timed out. Defaulting to first option.")
        else:
            user_choice = value_view.selected_value
        
        await asyncio.sleep(0.5)
        
        # Spin the wheel first (outcome determined before animation)
        outcome_color, outcome_number = self._spin_roulette()
        
        # === ENHANCED MULTI-STAGE ANIMATION ===
        
        # Stage 1: Dealer opening call
        dealer_call = self._get_dealer_call("opening")
        opening_embed = discord.Embed(
            title="🎲 Roulette Table",
            description=f"**{dealer_call}**",
            color=discord.Color.blue(),
        )
        spin_message = await channel.send(embed=opening_embed)
        await asyncio.sleep(0.8)
        
        # Stage 2-4: Fast spinning (3 cycles)
        spin_patterns = [
            "🔴 ⚫ 🔴 ⚫ 🟢 🔴 ⚫",
            "⚫ 🔴 ⚫ 🟢 🔴 ⚫ 🔴",
            "🔴 ⚫ 🟢 🔴 ⚫ 🔴 ⚫",
        ]
        for i, pattern in enumerate(spin_patterns):
            fast_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description=f"**{self._get_dealer_call('spinning')}**",
                color=discord.Color.blue(),
            )
            fast_embed.add_field(name="Wheel", value=pattern, inline=False)
            await spin_message.edit(embed=fast_embed)
            await asyncio.sleep(config.ROULETTE_ANIMATION_FAST_INTERVAL)
        
        # Stage 5-6: Medium speed (2 cycles)
        medium_patterns = [
            "⚫ 🟢 🔴 ⚫ 🔴 ⚫ 🔴",
            "🟢 🔴 ⚫ 🔴 ⚫ 🔴 ⚫",
        ]
        for pattern in medium_patterns:
            medium_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description="**The wheel is slowing down...**",
                color=discord.Color.orange(),
            )
            medium_embed.add_field(name="Wheel", value=pattern, inline=False)
            await spin_message.edit(embed=medium_embed)
            await asyncio.sleep(config.ROULETTE_ANIMATION_MEDIUM_INTERVAL)
        
        # Stage 7-8: Slow speed (2 cycles)
        slow_patterns = [
            "🔴 ⚫ 🔴 🟢 ⚫ 🔴",
            "⚫ 🔴 🟢 ⚫ 🔴 ⚫",
        ]
        for pattern in slow_patterns:
            slow_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description="**Ball is slowing...**",
                color=discord.Color.gold(),
            )
            slow_embed.add_field(name="Wheel", value=pattern, inline=False)
            await spin_message.edit(embed=slow_embed)
            await asyncio.sleep(config.ROULETTE_ANIMATION_SLOW_INTERVAL)
        
        # Stage 9: Physics fake-out (5% chance)
        if random.random() < config.ROULETTE_PHYSICS_FAKEOUT_CHANCE:
            fakeout_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description="**💥 The ball bounces off a peg… changes direction!**",
                color=discord.Color.purple(),
            )
            await spin_message.edit(embed=fakeout_embed)
            await asyncio.sleep(0.8)
        
        # Now process the result in database
        async with get_user_lock(player_id):
            async with get_session() as session:
                # Mark game as active
                await update_game_status(session, game_id, GameStatus.ACTIVE)
                
                user = await get_user_by_discord_id(session, player_id)
                
                # Calculate payout with new signature
                payout, is_win = self._calculate_payout(bet, bet_type, user_choice, outcome_number, outcome_color)
                
                # Update balance
                reason = TransactionReason.ROULETTE_WIN if is_win else TransactionReason.ROULETTE_LOSS
                await update_user_balance(
                    session,
                    user_id=user.id,
                    amount=payout,
                    reason=reason,
                    game_id=game_id,
                )
                
                # Award XP for wagering
                xp_earned = calculate_xp_reward(bet)
                user, tier_up = await add_user_xp(session, user.id, xp_earned)
                new_balance = user.balance
                
                # Update participant result
                participants = await get_duel_participants(session, game_id)
                participant = participants[0]
                await update_participant_result(
                    session,
                    participant_id=participant.id,
                    is_winner=is_win,
                )
                
                # Mark game as completed
                await update_game_status(session, game_id, GameStatus.COMPLETED)
                
                # Store tier-up info for notification
                tier_up_info = None
                if tier_up:
                    new_tier = get_level_tier(user.experience_points)
                    tier_up_info = new_tier
        
        # === STAGE 10: FINAL RESULT WITH ASCII BOARD ===
        
        # Determine embed color based on result
        if is_win:
            if outcome_color == RouletteChoice.GREEN:
                final_color = discord.Color.gold()
            else:
                final_color = discord.Color.green()
        else:
            final_color = discord.Color.red()
        
        # Get dealer closing call
        dealer_closing = self._get_dealer_call("win" if is_win else "loss")
        
        final_embed = discord.Embed(
            title=f"🎡 {dealer_closing}",
            color=final_color,
        )
        
        # Display result with ASCII board
        outcome_emoji = self._get_color_emoji(outcome_color)
        final_embed.add_field(
            name="Result",
            value=f"**The ball landed on:**\n{outcome_emoji} **{outcome_color.upper()} {outcome_number}**",
            inline=False,
        )
        
        # Add ASCII board
        board_display = self._create_roulette_board(outcome_number)
        final_embed.add_field(
            name="Roulette Wheel",
            value=board_display,
            inline=False,
        )
        
        # Format bet display based on type
        if bet_type == BetType.COLOR:
            bet_display = f"{self._get_color_emoji(user_choice)} **{user_choice.upper()}**"
        elif bet_type == BetType.ODD_EVEN:
            bet_display = f"{'1️⃣' if user_choice == OddEvenChoice.ODD else '2️⃣'} **{user_choice.upper()}**"
        else:  # HIGH_LOW
            range_text = "19-36" if user_choice == HighLowChoice.HIGH else "1-18"
            bet_display = f"{'⬆️' if user_choice == HighLowChoice.HIGH else '⬇️'} **{user_choice.upper()} ({range_text})**"
        
        final_embed.add_field(
            name="Your Bet",
            value=f"{bet_display} - {format_coins(bet)}",
            inline=False
        )
        
        # Show win/loss
        if is_win:
            if bet_type == BetType.COLOR and outcome_color == RouletteChoice.GREEN:
                result_text = "🎉 JACKPOT! You hit GREEN!"
            else:
                result_text = f"🎉 Winner!"
            
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
        
        # Determine payout multiplier for footer
        if bet_type == BetType.COLOR:
            multiplier = config.ROULETTE_PAYOUT_GREEN if user_choice == RouletteChoice.GREEN else config.ROULETTE_PAYOUT_RED_BLACK
        else:
            multiplier = config.ROULETTE_PAYOUT_RED_BLACK
        
        final_embed.set_footer(text=f"Bet: {format_coins(bet)} | +{xp_earned} XP | Pays {multiplier}x")
        final_embed.set_thumbnail(url=member.display_avatar.url)
        
        await spin_message.edit(embed=final_embed)
        
        # === STAGE 11: NEAR-MISS CHECK ===
        near_miss_msg = self._check_near_miss(bet_type, user_choice, outcome_number, outcome_color)
        if near_miss_msg and not is_win:
            await asyncio.sleep(0.5)
            await channel.send(near_miss_msg)
        
        # Send tier-up notification if occurred
        if tier_up_info:
            tier_embed = discord.Embed(
                title="🎉 TIER UP!",
                description=(
                    f"Congratulations {member.mention}!\n\n"
                    f"You've advanced to **{format_tier_badge(tier_up_info)}**!\n\n"
                    f"**New Max Bet:** {format_coins(tier_up_info.max_bet)}"
                ),
                color=discord.Color.gold(),
            )
            tier_embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=tier_embed)
    
    async def _run_multiplayer_game(
        self,
        channel: discord.TextChannel,
        game_id: int,
        player_ids: list[int],
        bet: int,
    ) -> None:
        """Execute multiplayer roulette game with enhanced animations and features."""
        async with get_session() as session:
            # Mark game as active
            await update_game_status(session, game_id, GameStatus.ACTIVE)
        
        # Each player selects their bet type and value sequentially
        player_bet_types: dict[int, str] = {}
        player_choices: dict[int, str] = {}
        
        for player_id in player_ids:
            member = await channel.guild.fetch_member(player_id)
            
            # Stage 1: Bet type selection
            type_embed = discord.Embed(
                title="🎰 Choose Your Bet Type",
                description=f"{member.display_name}, what type of bet do you want to make?",
                color=discord.Color.blue(),
            )
            type_view = BetTypeSelectionView(player_id=player_id)
            
            type_message = await channel.send(embed=type_embed, view=type_view)
            await type_view.wait()
            
            if not type_view.selected_type:
                # Timeout - default to color bet
                bet_type = BetType.COLOR
                await channel.send(f"⏰ {member.display_name} timed out. Defaulting to **COLOR BET**.")
            else:
                bet_type = type_view.selected_type
            
            player_bet_types[player_id] = bet_type
            await asyncio.sleep(0.3)
            
            # Stage 2: Bet value selection
            value_embed = discord.Embed(
                title="🎯 Choose Your Bet",
                description=f"{member.display_name}, make your choice!",
                color=discord.Color.green(),
            )
            value_view = BetValueSelectionView(player_id=player_id, bet_type=bet_type)
            
            value_message = await channel.send(embed=value_embed, view=value_view)
            await value_view.wait()
            
            if not value_view.selected_value:
                # Timeout - default based on bet type
                if bet_type == BetType.COLOR:
                    user_choice = RouletteChoice.RED
                elif bet_type == BetType.ODD_EVEN:
                    user_choice = OddEvenChoice.ODD
                else:
                    user_choice = HighLowChoice.HIGH
                await channel.send(f"⏰ {member.display_name} timed out. Defaulting to first option.")
            else:
                user_choice = value_view.selected_value
            
            player_choices[player_id] = user_choice
            await asyncio.sleep(0.5)
        
        # Show all player choices
        choices_embed = discord.Embed(
            title="🎰 All Bets Are In!",
            description="Here's what everyone bet:",
            color=discord.Color.blue(),
        )
        
        for player_id in player_ids:
            member = await channel.guild.fetch_member(player_id)
            bet_type = player_bet_types[player_id]
            user_choice = player_choices[player_id]
            
            # Format bet display based on type
            if bet_type == BetType.COLOR:
                bet_display = f"{self._get_color_emoji(user_choice)} **{user_choice.upper()}**"
            elif bet_type == BetType.ODD_EVEN:
                bet_display = f"{'1️⃣' if user_choice == OddEvenChoice.ODD else '2️⃣'} **{user_choice.upper()}**"
            else:  # HIGH_LOW
                range_text = "19-36" if user_choice == HighLowChoice.HIGH else "1-18"
                bet_display = f"{'⬆️' if user_choice == HighLowChoice.HIGH else '⬇️'} **{user_choice.upper()} ({range_text})**"
            
            choices_embed.add_field(
                name=f"{member.display_name}",
                value=f"{bet_display} - {format_coins(bet)}",
                inline=False,
            )
        
        await channel.send(embed=choices_embed)
        await asyncio.sleep(1.0)
        
        # Spin the wheel (ONE shared spin)
        outcome_color, outcome_number = self._spin_roulette()
        
        # === ENHANCED MULTI-STAGE ANIMATION ===
        
        # Stage 1: Dealer opening call
        dealer_call = self._get_dealer_call("opening")
        opening_embed = discord.Embed(
            title="🎲 Roulette Table",
            description=f"**{dealer_call}**",
            color=discord.Color.blue(),
        )
        spin_message = await channel.send(embed=opening_embed)
        await asyncio.sleep(0.8)
        
        # Stage 2-4: Fast spinning (3 cycles)
        spin_patterns = [
            "🔴 ⚫ 🔴 ⚫ 🟢 🔴 ⚫",
            "⚫ 🔴 ⚫ 🟢 🔴 ⚫ 🔴",
            "🔴 ⚫ 🟢 🔴 ⚫ 🔴 ⚫",
        ]
        for i, pattern in enumerate(spin_patterns):
            fast_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description=f"**{self._get_dealer_call('spinning')}**",
                color=discord.Color.blue(),
            )
            fast_embed.add_field(name="Wheel", value=pattern, inline=False)
            await spin_message.edit(embed=fast_embed)
            await asyncio.sleep(config.ROULETTE_ANIMATION_FAST_INTERVAL)
        
        # Stage 5-6: Medium speed (2 cycles)
        medium_patterns = [
            "⚫ 🟢 🔴 ⚫ 🔴 ⚫ 🔴",
            "🟢 🔴 ⚫ 🔴 ⚫ 🔴 ⚫",
        ]
        for pattern in medium_patterns:
            medium_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description="**The wheel is slowing down...**",
                color=discord.Color.orange(),
            )
            medium_embed.add_field(name="Wheel", value=pattern, inline=False)
            await spin_message.edit(embed=medium_embed)
            await asyncio.sleep(config.ROULETTE_ANIMATION_MEDIUM_INTERVAL)
        
        # Stage 7-8: Slow speed (2 cycles)
        slow_patterns = [
            "🔴 ⚫ 🔴 🟢 ⚫ 🔴",
            "⚫ 🔴 🟢 ⚫ 🔴 ⚫",
        ]
        for pattern in slow_patterns:
            slow_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description="**Ball is slowing...**",
                color=discord.Color.gold(),
            )
            slow_embed.add_field(name="Wheel", value=pattern, inline=False)
            await spin_message.edit(embed=slow_embed)
            await asyncio.sleep(config.ROULETTE_ANIMATION_SLOW_INTERVAL)
        
        # Stage 9: Physics fake-out (5% chance)
        if random.random() < config.ROULETTE_PHYSICS_FAKEOUT_CHANCE:
            fakeout_embed = discord.Embed(
                title="🎡 Roulette Wheel",
                description="**💥 The ball bounces off a peg… changes direction!**",
                color=discord.Color.purple(),
            )
            await spin_message.edit(embed=fakeout_embed)
            await asyncio.sleep(0.8)
        
        # Stage 10: Reveal result with ASCII board
        result_embed = discord.Embed(
            title="🎡 Roulette Result 🎡",
            color=discord.Color.gold(),
        )
        
        outcome_emoji = self._get_color_emoji(outcome_color)
        result_embed.add_field(
            name="Result",
            value=f"**The ball landed on:**\n{outcome_emoji} **{outcome_color.upper()} {outcome_number}**",
            inline=False,
        )
        
        # Add ASCII board
        board_display = self._create_roulette_board(outcome_number)
        result_embed.add_field(
            name="Roulette Wheel",
            value=board_display,
            inline=False,
        )
        
        await spin_message.edit(embed=result_embed)
        await asyncio.sleep(1.0)
        
        # Calculate payouts and update balances for all players
        tier_ups = []  # Store tier-up info for notifications
        near_miss_messages = []  # Store near-miss messages for each player
        results_embed = discord.Embed(
            title="🏁 Game Results",
            color=discord.Color.gold(),
        )
        
        async with get_session() as session:
            for player_id in player_ids:
                member = await channel.guild.fetch_member(player_id)
                user = await get_user_by_discord_id(session, player_id)
                bet_type = player_bet_types[player_id]
                user_choice = player_choices[player_id]
                
                # Calculate payout for this player with new signature
                payout, is_win = self._calculate_payout(bet, bet_type, user_choice, outcome_number, outcome_color)
                
                # Update balance
                async with get_user_lock(player_id):
                    reason = TransactionReason.ROULETTE_WIN if is_win else TransactionReason.ROULETTE_LOSS
                    await update_user_balance(
                        session,
                        user_id=user.id,
                        amount=payout,
                        reason=reason,
                        game_id=game_id,
                    )
                    
                    # Award XP for wagering
                    xp_earned = calculate_xp_reward(bet)
                    user, tier_up = await add_user_xp(session, user.id, xp_earned)
                    if tier_up:
                        tier_info = get_level_tier(user.experience_points)
                        tier_ups.append((member, tier_info))
                    
                    # Update participant result
                    participants = await get_duel_participants(session, game_id)
                    participant = next(p for p in participants if p.user_id == user.id)
                    await update_participant_result(
                        session,
                        participant_id=participant.id,
                        is_winner=is_win,
                    )
                    
                    # Get updated balance
                    user = await get_user_by_id(session, user.id)
                
                # Check for near-miss
                near_miss = self._check_near_miss(bet_type, user_choice, outcome_number, outcome_color)
                if near_miss and not is_win:
                    near_miss_messages.append(f"{member.display_name}: {near_miss}")
                
                # Format bet display based on type
                if bet_type == BetType.COLOR:
                    bet_display = f"{self._get_color_emoji(user_choice)} **{user_choice.upper()}**"
                elif bet_type == BetType.ODD_EVEN:
                    bet_display = f"{'1️⃣' if user_choice == OddEvenChoice.ODD else '2️⃣'} **{user_choice.upper()}**"
                else:  # HIGH_LOW
                    range_text = "19-36" if user_choice == HighLowChoice.HIGH else "1-18"
                    bet_display = f"{'⬆️' if user_choice == HighLowChoice.HIGH else '⬇️'} **{user_choice.upper()} ({range_text})**"
                
                # Format result for this player
                if is_win:
                    if bet_type == BetType.COLOR and outcome_color == RouletteChoice.GREEN:
                        result_icon = "💎"
                        result_text = f"**JACKPOT!** Won {format_coins(payout)}"
                    else:
                        result_icon = "✅"
                        result_text = f"**WIN!** Won {format_coins(payout)}"
                else:
                    result_icon = "❌"
                    result_text = f"**LOSS** Lost {format_coins(bet)}"
                
                results_embed.add_field(
                    name=f"{result_icon} {member.display_name}",
                    value=(
                        f"Bet: {bet_display}\n"
                        f"{result_text}\n"
                        f"Balance: {format_coins(user.balance)}"
                    ),
                    inline=False,
                )
            
            # Mark game as completed
            await update_game_status(session, game_id, GameStatus.COMPLETED)
        
        await channel.send(embed=results_embed)
        
        # Send near-miss messages if any
        if near_miss_messages:
            await asyncio.sleep(0.5)
            near_miss_embed = discord.Embed(
                title="😱 So Close!",
                description="\n".join(near_miss_messages),
                color=discord.Color.orange(),
            )
            await channel.send(embed=near_miss_embed)
        
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


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Roulette(bot))

