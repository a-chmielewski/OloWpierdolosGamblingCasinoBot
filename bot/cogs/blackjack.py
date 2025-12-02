"""Blackjack cog - Classic 21 card game against the dealer."""

import asyncio
import json
import logging
from typing import Optional, List, Dict

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
    update_game_status,
    update_game_message_id,
    add_duel_participant,
    get_duel_participants,
    update_participant_result,
)
from database.models import GameType, GameStatus, TransactionReason
from utils.helpers import format_coins, get_user_lock
from utils.card_utils import Deck, Hand, format_hand_display, calculate_winner

logger = logging.getLogger(__name__)


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
    """View with button to join a pending blackjack game."""
    
    def __init__(self, game_id: int, bet_amount: int, existing_player_ids: List[int]):
        super().__init__(timeout=config.BLACKJACK_JOIN_TIMEOUT_SECONDS)
        self.game_id = game_id
        self.bet_amount = bet_amount
        self.existing_player_ids = existing_player_ids
        self.new_players: List[int] = []
    
    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="🃏")
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """Join the blackjack game."""
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


class Blackjack(commands.Cog):
    """Blackjack commands for playing 21 against the dealer."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(
        name="blackjack",
        description="Play Blackjack (21) against the dealer - solo or multiplayer"
    )
    @app_commands.describe(bet="The amount to bet")
    async def blackjack(
        self,
        interaction: discord.Interaction,
        bet: int,
    ) -> None:
        """Start a blackjack game."""
        # Validate bet amount
        if bet < config.BLACKJACK_MIN_BET:
            await interaction.response.send_message(
                f"❌ Minimum bet is {format_coins(config.BLACKJACK_MIN_BET)}!",
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
                game_type=GameType.BLACKJACK,
                creator_user_id=user.id,
                channel_id=interaction.channel_id,
                data=game_data,
            )
            
            # Add creator as first participant
            await add_duel_participant(session, game.id, user.id, bet)
            
            game_id = game.id
        
        # Create mode selection embed
        embed = discord.Embed(
            title="🃏 Blackjack Game",
            description=(
                f"**{interaction.user.display_name}** wants to play Blackjack!\n\n"
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
            # Start solo game immediately
            embed = discord.Embed(
                title="🎴 Solo Blackjack",
                description=f"{interaction.user.display_name} is playing solo against the dealer!",
                color=discord.Color.purple(),
            )
            await message.edit(embed=embed, view=None)
            await self._run_game(interaction.channel, game_id, [interaction.user.id])
        
        elif view.mode == "multiplayer":
            # Wait for players to join
            embed = discord.Embed(
                title="👥 Multiplayer Blackjack - Waiting for Players",
                description=(
                    f"**Bet Amount:** {format_coins(bet)}\n"
                    f"**Creator:** {interaction.user.display_name}\n\n"
                    f"Other players can join by clicking the button below!\n"
                    f"Game starts in {config.BLACKJACK_JOIN_TIMEOUT_SECONDS} seconds or when creator starts."
                ),
                color=discord.Color.gold(),
            )
            
            join_view = JoinGameView(
                game_id=game_id,
                bet_amount=bet,
                existing_player_ids=[interaction.user.id],
            )
            
            await message.edit(embed=embed, view=join_view)
            await join_view.wait()
            
            # Get all participants
            async with get_session() as session:
                participants = await get_duel_participants(session, game_id)
                player_ids = [interaction.user.id] + join_view.new_players
            
            if len(player_ids) == 1:
                embed = discord.Embed(
                    title="🎴 Starting Solo Game",
                    description="No other players joined. Starting solo game!",
                    color=discord.Color.blue(),
                )
            else:
                embed = discord.Embed(
                    title="🃏 Starting Multiplayer Game",
                    description=f"{len(player_ids)} players joined! Let's play!",
                    color=discord.Color.green(),
                )
            
            await message.edit(embed=embed, view=None)
            await self._run_game(interaction.channel, game_id, player_ids)
        
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
    
    async def _run_game(
        self,
        channel: discord.TextChannel,
        game_id: int,
        player_discord_ids: List[int],
    ) -> None:
        """Execute the blackjack game sequence."""
        async with get_session() as session:
            # Mark game as active
            await update_game_status(session, game_id, GameStatus.ACTIVE)
            
            # Get participants
            participants = await get_duel_participants(session, game_id)
            bet_amount = participants[0].bet_amount if participants else 0
        
        # Initialize game
        deck = Deck(num_decks=1)
        player_hands: Dict[int, Hand] = {}
        dealer_hand = Hand()
        
        # Deal initial cards
        await self._deal_initial_cards(channel, deck, player_discord_ids, player_hands, dealer_hand, bet_amount)
        
        await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS)
        
        # Check for dealer blackjack
        if dealer_hand.is_blackjack():
            await self._handle_dealer_blackjack(channel, game_id, player_discord_ids, player_hands, dealer_hand)
            return
        
        # Each player takes their turn
        for player_id in player_discord_ids:
            if player_hands[player_id].is_blackjack():
                # Player has blackjack, skip their turn
                continue
            
            await self._player_turn(channel, player_id, player_hands[player_id], dealer_hand, deck)
            await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS * 0.5)
        
        # Dealer's turn
        await self._dealer_turn(channel, dealer_hand, deck)
        
        # Calculate results and finalize
        await self._finalize_game(channel, game_id, player_discord_ids, player_hands, dealer_hand)
    
    async def _deal_initial_cards(
        self,
        channel: discord.TextChannel,
        deck: Deck,
        player_ids: List[int],
        player_hands: Dict[int, Hand],
        dealer_hand: Hand,
        bet_amount: int,
    ) -> None:
        """Deal initial 2 cards to each player and dealer."""
        embed = discord.Embed(
            title="🎴 Dealing Cards...",
            description="The dealer is shuffling and dealing cards.",
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed)
        
        await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS)
        
        # Initialize hands for all players
        for player_id in player_ids:
            player_hands[player_id] = Hand(bet=bet_amount)
        
        # Deal first card to each player
        for player_id in player_ids:
            card = deck.deal()
            player_hands[player_id].add_card(card)
        
        # Deal first card to dealer (face up)
        dealer_hand.add_card(deck.deal())
        
        # Deal second card to each player
        for player_id in player_ids:
            card = deck.deal()
            player_hands[player_id].add_card(card)
        
        # Deal second card to dealer (face down)
        dealer_hand.add_card(deck.deal())
        
        # Show initial hands
        embed = discord.Embed(
            title="🃏 Initial Deal",
            color=discord.Color.blue(),
        )
        
        # Show dealer's hand (one card hidden)
        embed.add_field(
            name="🎩 Dealer",
            value=dealer_hand.format_cards(hide_first=True),
            inline=False,
        )
        
        # Show each player's hand
        for player_id in player_ids:
            member = await channel.guild.fetch_member(player_id)
            hand = player_hands[player_id]
            hand_display = format_hand_display(hand)
            embed.add_field(
                name=f"🎴 {member.display_name}",
                value=hand_display,
                inline=False,
            )
        
        await channel.send(embed=embed)
    
    async def _player_turn(
        self,
        channel: discord.TextChannel,
        player_id: int,
        hand: Hand,
        dealer_hand: Hand,
        deck: Deck,
    ) -> None:
        """Handle a player's turn with reaction-based actions."""
        member = await channel.guild.fetch_member(player_id)
        
        while not hand.is_stand and not hand.is_bust():
            # Create turn embed
            embed = discord.Embed(
                title=f"🎴 {member.display_name}'s Turn",
                description=(
                    f"**Your Hand:** {format_hand_display(hand)}\n"
                    f"**Dealer Shows:** {dealer_hand.cards[1]}\n\n"
                    f"React with your action:"
                ),
                color=discord.Color.green(),
            )
            
            message = await channel.send(embed=embed)
            
            # Add reaction options
            await message.add_reaction("👊")  # Hit
            await message.add_reaction("✋")  # Stand
            
            if hand.can_double():
                await message.add_reaction("💰")  # Double Down
            
            if hand.can_split():
                await message.add_reaction("✂️")  # Split (not implemented in basic version)
            
            def check(reaction, user):
                return (
                    user.id == player_id
                    and reaction.message.id == message.id
                    and str(reaction.emoji) in ["👊", "✋", "💰", "✂️"]
                )
            
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add",
                    timeout=config.BLACKJACK_ACTION_TIMEOUT_SECONDS,
                    check=check,
                )
                
                action = str(reaction.emoji)
                
                if action == "👊":  # Hit
                    card = deck.deal()
                    hand.add_card(card)
                    
                    result_embed = discord.Embed(
                        title=f"👊 {member.display_name} Hits!",
                        description=f"Drew: {card}\n\n{format_hand_display(hand)}",
                        color=discord.Color.blue(),
                    )
                    await channel.send(embed=result_embed)
                    
                    if hand.is_bust():
                        bust_embed = discord.Embed(
                            title=f"💥 {member.display_name} Busts!",
                            description=f"Hand value: {hand.value()}",
                            color=discord.Color.red(),
                        )
                        await channel.send(embed=bust_embed)
                        break
                
                elif action == "✋":  # Stand
                    hand.is_stand = True
                    
                    stand_embed = discord.Embed(
                        title=f"✋ {member.display_name} Stands",
                        description=f"Final hand: {format_hand_display(hand)}",
                        color=discord.Color.blue(),
                    )
                    await channel.send(embed=stand_embed)
                    break
                
                elif action == "💰" and hand.can_double():  # Double Down
                    hand.is_doubled = True
                    hand.bet *= 2
                    card = deck.deal()
                    hand.add_card(card)
                    hand.is_stand = True
                    
                    double_embed = discord.Embed(
                        title=f"💰 {member.display_name} Doubles Down!",
                        description=f"Bet doubled to {format_coins(hand.bet)}\nDrew: {card}\n\n{format_hand_display(hand)}",
                        color=discord.Color.gold(),
                    )
                    await channel.send(embed=double_embed)
                    
                    if hand.is_bust():
                        bust_embed = discord.Embed(
                            title=f"💥 {member.display_name} Busts!",
                            description=f"Hand value: {hand.value()}",
                            color=discord.Color.red(),
                        )
                        await channel.send(embed=bust_embed)
                    break
                
                elif action == "✂️" and hand.can_split():  # Split (simplified - not fully implemented)
                    split_embed = discord.Embed(
                        title="✂️ Split Not Available",
                        description="Split feature coming soon! Please choose another action.",
                        color=discord.Color.orange(),
                    )
                    await channel.send(embed=split_embed)
                    continue
                
                await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS * 0.5)
            
            except asyncio.TimeoutError:
                # Auto-stand on timeout
                hand.is_stand = True
                
                timeout_embed = discord.Embed(
                    title=f"⏰ {member.display_name} Timed Out",
                    description=f"Automatically standing with: {format_hand_display(hand)}",
                    color=discord.Color.orange(),
                )
                await channel.send(embed=timeout_embed)
                break
    
    async def _dealer_turn(
        self,
        channel: discord.TextChannel,
        dealer_hand: Hand,
        deck: Deck,
    ) -> None:
        """Execute dealer's turn (reveal and hit until 17+)."""
        embed = discord.Embed(
            title="🎩 Dealer's Turn",
            description="Revealing dealer's hand...",
            color=discord.Color.purple(),
        )
        await channel.send(embed=embed)
        
        await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS)
        
        # Reveal dealer's hand
        reveal_embed = discord.Embed(
            title="🎩 Dealer Reveals",
            description=format_hand_display(dealer_hand),
            color=discord.Color.purple(),
        )
        await channel.send(embed=reveal_embed)
        
        await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS)
        
        # Dealer hits until 17+
        while dealer_hand.value() < config.BLACKJACK_DEALER_STAND_VALUE:
            card = deck.deal()
            dealer_hand.add_card(card)
            
            hit_embed = discord.Embed(
                title="🎩 Dealer Hits",
                description=f"Drew: {card}\n\n{format_hand_display(dealer_hand)}",
                color=discord.Color.purple(),
            )
            await channel.send(embed=hit_embed)
            
            await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS)
            
            if dealer_hand.is_bust():
                bust_embed = discord.Embed(
                    title="💥 Dealer Busts!",
                    description=f"Dealer busted with {dealer_hand.value()}",
                    color=discord.Color.red(),
                )
                await channel.send(embed=bust_embed)
                break
        
        if not dealer_hand.is_bust():
            stand_embed = discord.Embed(
                title="🎩 Dealer Stands",
                description=format_hand_display(dealer_hand),
                color=discord.Color.purple(),
            )
            await channel.send(embed=stand_embed)
    
    async def _handle_dealer_blackjack(
        self,
        channel: discord.TextChannel,
        game_id: int,
        player_ids: List[int],
        player_hands: Dict[int, Hand],
        dealer_hand: Hand,
    ) -> None:
        """Handle the case when dealer has blackjack."""
        # Reveal dealer blackjack
        reveal_embed = discord.Embed(
            title="🎩 Dealer Has Blackjack!",
            description=format_hand_display(dealer_hand),
            color=discord.Color.red(),
        )
        await channel.send(embed=reveal_embed)
        
        await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS)
        
        # Process each player
        async with get_session() as session:
            for player_id in player_ids:
                user = await get_user_by_discord_id(session, player_id)
                hand = player_hands[player_id]
                
                if hand.is_blackjack():
                    # Push - return bet
                    result = "push"
                    payout = hand.bet
                else:
                    # Player loses
                    result = "loss"
                    payout = 0
                
                # Update balance
                if result == "push":
                    # No balance change for push
                    pass
                else:
                    await update_user_balance(
                        session,
                        user_id=user.id,
                        amount=-hand.bet,
                        reason=TransactionReason.BLACKJACK_LOSS,
                        game_id=game_id,
                    )
                
                # Update participant
                participants = await get_duel_participants(session, game_id)
                participant = next(p for p in participants if p.user_id == user.id)
                await update_participant_result(
                    session,
                    participant_id=participant.id,
                    is_winner=(result == "push"),
                )
            
            await update_game_status(session, game_id, GameStatus.COMPLETED)
        
        # Show final results
        await self._show_final_results(channel, player_ids, player_hands, dealer_hand)
    
    async def _finalize_game(
        self,
        channel: discord.TextChannel,
        game_id: int,
        player_ids: List[int],
        player_hands: Dict[int, Hand],
        dealer_hand: Hand,
    ) -> None:
        """Calculate payouts and update balances."""
        await asyncio.sleep(config.BLACKJACK_CARD_DELAY_SECONDS)
        
        embed = discord.Embed(
            title="🏁 Game Results",
            color=discord.Color.gold(),
        )
        
        async with get_session() as session:
            for player_id in player_ids:
                member = await channel.guild.fetch_member(player_id)
                user = await get_user_by_discord_id(session, player_id)
                hand = player_hands[player_id]
                
                # Calculate result
                result, multiplier = calculate_winner(hand, dealer_hand)
                payout = int(hand.bet * multiplier)
                profit = payout - hand.bet
                
                # Update balance
                if profit != 0:
                    reason = TransactionReason.BLACKJACK_WIN if profit > 0 else TransactionReason.BLACKJACK_LOSS
                    await update_user_balance(
                        session,
                        user_id=user.id,
                        amount=profit,
                        reason=reason,
                        game_id=game_id,
                    )
                
                # Update participant
                participants = await get_duel_participants(session, game_id)
                participant = next(p for p in participants if p.user_id == user.id)
                await update_participant_result(
                    session,
                    participant_id=participant.id,
                    is_winner=(profit > 0),
                )
                
                # Get updated balance
                user = await get_user_by_id(session, user.id)
                
                # Format result
                if result == "blackjack":
                    result_text = f"🃏 **BLACKJACK!** Won {format_coins(profit)}"
                    result_color = "🥇"
                elif result == "win":
                    result_text = f"✅ **WIN!** Won {format_coins(profit)}"
                    result_color = "🎉"
                elif result == "push":
                    result_text = f"🤝 **PUSH** (Tie)"
                    result_color = "⚖️"
                else:  # loss
                    result_text = f"❌ **LOSS** Lost {format_coins(hand.bet)}"
                    result_color = "💸"
                
                embed.add_field(
                    name=f"{result_color} {member.display_name}",
                    value=(
                        f"{result_text}\n"
                        f"Hand: {format_hand_display(hand, show_value=False)}\n"
                        f"New Balance: {format_coins(user.balance)}"
                    ),
                    inline=False,
                )
            
            await update_game_status(session, game_id, GameStatus.COMPLETED)
        
        # Add dealer's final hand
        embed.add_field(
            name="🎩 Dealer",
            value=format_hand_display(dealer_hand),
            inline=False,
        )
        
        await channel.send(embed=embed)
    
    async def _show_final_results(
        self,
        channel: discord.TextChannel,
        player_ids: List[int],
        player_hands: Dict[int, Hand],
        dealer_hand: Hand,
    ) -> None:
        """Show final results summary."""
        embed = discord.Embed(
            title="🏁 Final Results",
            color=discord.Color.blue(),
        )
        
        # Show dealer
        embed.add_field(
            name="🎩 Dealer",
            value=format_hand_display(dealer_hand),
            inline=False,
        )
        
        # Show each player
        for player_id in player_ids:
            member = await channel.guild.fetch_member(player_id)
            hand = player_hands[player_id]
            embed.add_field(
                name=f"🎴 {member.display_name}",
                value=format_hand_display(hand),
                inline=False,
            )
        
        await channel.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Blackjack(bot))

