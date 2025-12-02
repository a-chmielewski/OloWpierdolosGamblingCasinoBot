"""Racing utilities for Animal Racing game."""

import random
from typing import Optional
from config import config


class Racer:
    """Represents a racing animal with speed characteristics."""
    
    def __init__(self, name: str, emoji: str, min_speed: int, max_speed: int):
        self.name = name
        self.emoji = emoji
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.position = 0
    
    def move(self) -> int:
        """Move the racer forward by a random amount within speed range."""
        distance = random.randint(self.min_speed, self.max_speed)
        self.position += distance
        return distance
    
    def __repr__(self) -> str:
        return f"<Racer({self.name}, pos={self.position})>"


class RaceTrack:
    """Manages a race with multiple racers."""
    
    def __init__(self, track_length: int = config.RACE_TRACK_LENGTH):
        self.track_length = track_length
        self.racers: list[Racer] = []
        self.winner: Optional[Racer] = None
        
        # Initialize all racers from config
        for racer_config in config.RACE_RACERS:
            racer = Racer(
                name=racer_config["name"],
                emoji=racer_config["emoji"],
                min_speed=racer_config["min_speed"],
                max_speed=racer_config["max_speed"],
            )
            self.racers.append(racer)
    
    def update(self) -> None:
        """Update all racers' positions."""
        for racer in self.racers:
            racer.move()
    
    def check_winner(self) -> Optional[Racer]:
        """Check if any racer has finished. Returns winner or None."""
        for racer in self.racers:
            if racer.position >= self.track_length:
                if self.winner is None or racer.position > self.winner.position:
                    self.winner = racer
        return self.winner
    
    def get_racer_by_emoji(self, emoji: str) -> Optional[Racer]:
        """Get a racer by their emoji."""
        for racer in self.racers:
            if racer.emoji == emoji:
                return racer
        return None
    
    def get_racer_by_name(self, name: str) -> Optional[Racer]:
        """Get a racer by their name."""
        for racer in self.racers:
            if racer.name.lower() == name.lower():
                return racer
        return None
    
    def get_standings(self) -> list[Racer]:
        """Get racers sorted by position (leader first)."""
        return sorted(self.racers, key=lambda r: r.position, reverse=True)


def format_progress_bar(position: int, track_length: int, bar_length: int = config.RACE_PROGRESS_BAR_LENGTH) -> str:
    """
    Create a visual progress bar for a racer.
    
    Args:
        position: Current position of the racer
        track_length: Total length of the track
        bar_length: Length of the progress bar in characters
    
    Returns:
        A progress bar string like "▓▓▓▓░░░░░░"
    """
    # Calculate filled portion
    progress = min(position / track_length, 1.0)
    filled = int(progress * bar_length)
    empty = bar_length - filled
    
    return "▓" * filled + "░" * empty


def format_race_display(racer: Racer, track_length: int, is_player_bet: bool = False, display_emoji: str = None) -> str:
    """
    Format a single racer's race display line.
    
    Args:
        racer: The racer to display
        track_length: Total length of the track
        is_player_bet: Whether a player has bet on this racer
        display_emoji: Optional emoji string to use instead of racer.emoji
    
    Returns:
        A formatted string like "🐢 Turtle [▓▓▓░░░░░░░] 34%"
    """
    progress_bar = format_progress_bar(racer.position, track_length)
    percentage = min(int((racer.position / track_length) * 100), 100)
    
    # Add indicator if players bet on this racer
    bet_indicator = " 💰" if is_player_bet else ""
    
    # Use display_emoji if provided, otherwise use racer.emoji
    emoji_str = display_emoji if display_emoji is not None else racer.emoji
    
    return f"{emoji_str} **{racer.name}** [{progress_bar}] {percentage}%{bet_indicator}"


def get_racer_config_by_emoji(emoji: str) -> Optional[dict]:
    """Get racer configuration from config by emoji."""
    for racer_config in config.RACE_RACERS:
        if racer_config["emoji"] == emoji:
            return racer_config
    return None


def get_racer_config_by_name(name: str) -> Optional[dict]:
    """Get racer configuration from config by name."""
    for racer_config in config.RACE_RACERS:
        if racer_config["name"].lower() == name.lower():
            return racer_config
    return None

