"""Card utilities for Blackjack game."""

import random
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


# Card emoji mappings for visual display
CARD_EMOJIS = {
    # Hearts
    ("A", "♥️"): "A❤️", ("2", "♥️"): "2❤️", ("3", "♥️"): "3❤️", ("4", "♥️"): "4❤️",
    ("5", "♥️"): "5❤️", ("6", "♥️"): "6❤️", ("7", "♥️"): "7❤️", ("8", "♥️"): "8❤️",
    ("9", "♥️"): "9❤️", ("10", "♥️"): "10❤️", ("J", "♥️"): "J❤️", ("Q", "♥️"): "Q❤️", ("K", "♥️"): "K❤️",
    
    # Diamonds
    ("A", "♦️"): "A♦️", ("2", "♦️"): "2♦️", ("3", "♦️"): "3♦️", ("4", "♦️"): "4♦️",
    ("5", "♦️"): "5♦️", ("6", "♦️"): "6♦️", ("7", "♦️"): "7♦️", ("8", "♦️"): "8♦️",
    ("9", "♦️"): "9♦️", ("10", "♦️"): "10♦️", ("J", "♦️"): "J♦️", ("Q", "♦️"): "Q♦️", ("K", "♦️"): "K♦️",
    
    # Clubs
    ("A", "♣️"): "A♣️", ("2", "♣️"): "2♣️", ("3", "♣️"): "3♣️", ("4", "♣️"): "4♣️",
    ("5", "♣️"): "5♣️", ("6", "♣️"): "6♣️", ("7", "♣️"): "7♣️", ("8", "♣️"): "8♣️",
    ("9", "♣️"): "9♣️", ("10", "♣️"): "10♣️", ("J", "♣️"): "J♣️", ("Q", "♣️"): "Q♣️", ("K", "♣️"): "K♣️",
    
    # Spades
    ("A", "♠️"): "A♠️", ("2", "♠️"): "2♠️", ("3", "♠️"): "3♠️", ("4", "♠️"): "4♠️",
    ("5", "♠️"): "5♠️", ("6", "♠️"): "6♠️", ("7", "♠️"): "7♠️", ("8", "♠️"): "8♠️",
    ("9", "♠️"): "9♠️", ("10", "♠️"): "10♠️", ("J", "♠️"): "J♠️", ("Q", "♠️"): "Q♠️", ("K", "♠️"): "K♠️",
}

CARD_BACK_EMOJI = "🂠"


@dataclass
class Card:
    """Represents a playing card."""
    rank: str  # "A", "2"-"10", "J", "Q", "K"
    suit: str  # "♥️", "♦️", "♣️", "♠️"
    
    def __str__(self) -> str:
        """Get the emoji representation of the card."""
        return CARD_EMOJIS.get((self.rank, self.suit), f"{self.rank}{self.suit}")
    
    def value(self) -> int:
        """Get the base value of the card (Aces are 11 by default)."""
        if self.rank == "A":
            return 11
        elif self.rank in ["J", "Q", "K"]:
            return 10
        else:
            return int(self.rank)


@dataclass
class Hand:
    """Represents a blackjack hand."""
    cards: List[Card] = field(default_factory=list)
    bet: int = 0
    is_doubled: bool = False
    is_split: bool = False
    is_stand: bool = False
    
    def add_card(self, card: Card) -> None:
        """Add a card to the hand."""
        self.cards.append(card)
    
    def value(self) -> int:
        """
        Calculate the best possible value of the hand.
        Aces are counted as 11 or 1 to get the best value under 21.
        """
        total = sum(card.value() for card in self.cards)
        aces = sum(1 for card in self.cards if card.rank == "A")
        
        # Adjust for aces - convert 11 to 1 as needed
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        
        return total
    
    def is_blackjack(self) -> bool:
        """Check if this is a natural blackjack (21 with 2 cards)."""
        return len(self.cards) == 2 and self.value() == 21
    
    def is_bust(self) -> bool:
        """Check if the hand is bust (over 21)."""
        return self.value() > 21
    
    def can_split(self) -> bool:
        """Check if the hand can be split (two cards of same rank)."""
        return len(self.cards) == 2 and self.cards[0].rank == self.cards[1].rank
    
    def can_double(self) -> bool:
        """Check if the hand can be doubled (only on first action with 2 cards)."""
        return len(self.cards) == 2 and not self.is_doubled
    
    def format_cards(self, hide_first: bool = False) -> str:
        """Format the cards for display."""
        if not self.cards:
            return "No cards"
        
        if hide_first:
            return f"{CARD_BACK_EMOJI} {' '.join(str(card) for card in self.cards[1:])}"
        else:
            return " ".join(str(card) for card in self.cards)
    
    def __str__(self) -> str:
        """String representation with cards and value."""
        return f"{self.format_cards()} (Value: {self.value()})"


class Deck:
    """Represents a deck of playing cards."""
    
    RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
    SUITS = ["♥️", "♦️", "♣️", "♠️"]
    
    def __init__(self, num_decks: int = 1):
        """Initialize a deck with the specified number of standard decks."""
        self.num_decks = num_decks
        self.cards: List[Card] = []
        self.reset()
    
    def reset(self) -> None:
        """Reset and shuffle the deck."""
        self.cards = []
        for _ in range(self.num_decks):
            for suit in self.SUITS:
                for rank in self.RANKS:
                    self.cards.append(Card(rank=rank, suit=suit))
        self.shuffle()
    
    def shuffle(self) -> None:
        """Shuffle the deck."""
        random.shuffle(self.cards)
    
    def deal(self) -> Optional[Card]:
        """Deal one card from the deck."""
        if not self.cards:
            return None
        return self.cards.pop()
    
    def remaining(self) -> int:
        """Get the number of remaining cards."""
        return len(self.cards)


def format_hand_display(hand: Hand, hide_first: bool = False, show_value: bool = True) -> str:
    """Format a hand for display with optional value."""
    cards_str = hand.format_cards(hide_first=hide_first)
    if hide_first or not show_value:
        return cards_str
    
    value = hand.value()
    if hand.is_blackjack():
        return f"{cards_str} **BLACKJACK!** 🃏"
    elif hand.is_bust():
        return f"{cards_str} **BUST!** 💥 ({value})"
    else:
        return f"{cards_str} ({value})"


def calculate_winner(player_hand: Hand, dealer_hand: Hand) -> Tuple[str, float]:
    """
    Calculate the winner and payout multiplier.
    Returns (result, multiplier) where:
    - result: "win", "loss", "push", "blackjack"
    - multiplier: 0 for loss, 1 for push, 2 for win, 2.5 for blackjack
    """
    player_value = player_hand.value()
    dealer_value = dealer_hand.value()
    
    # Player bust always loses
    if player_hand.is_bust():
        return "loss", 0
    
    # Player blackjack
    if player_hand.is_blackjack():
        if dealer_hand.is_blackjack():
            return "push", 1  # Both have blackjack, push
        else:
            return "blackjack", 2.5  # Player blackjack wins 3:2 (bet + 1.5x)
    
    # Dealer bust and player not bust
    if dealer_hand.is_bust():
        return "win", 2  # Regular win pays 1:1 (bet + 1x)
    
    # Neither bust, compare values
    if player_value > dealer_value:
        return "win", 2
    elif player_value < dealer_value:
        return "loss", 0
    else:
        return "push", 1  # Tie

