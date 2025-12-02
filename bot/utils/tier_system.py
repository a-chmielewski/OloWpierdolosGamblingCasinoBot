"""Tier system for progressive bet limits."""

from dataclasses import dataclass
from typing import Optional

from config import config


@dataclass
class TierInfo:
    """Information about a tier."""
    tier_number: int
    tier_name: str
    tier_emoji: str
    max_bet: int
    min_balance: int
    max_balance: Optional[int]
    min_xp: int
    max_xp: Optional[int]


# Tier definitions (Casino-style naming)
TIER_DEFINITIONS = [
    # tier_number, name, emoji, max_bet, min_balance, max_balance, min_xp, max_xp
    (1, "Newcomer", "🎲", 5_000, 0, 100_000, 0, 5_000),
    (2, "Regular", "🎰", 15_000, 100_001, 300_000, 5_000, 20_000),
    (3, "High Roller", "💰", 40_000, 300_001, 750_000, 20_000, 75_000),
    (4, "VIP", "👑", 100_000, 750_001, 2_000_000, 75_000, 250_000),
    (5, "Diamond", "💎", 300_000, 2_000_001, 5_000_000, 250_000, 750_000),
    (6, "Elite", "⭐", 750_000, 5_000_001, 10_000_000, 750_000, 2_000_000),
    (7, "Legendary", "🏆", 999_999_999, 10_000_001, None, 2_000_000, None),
]


def _build_tier_info(tier_tuple: tuple) -> TierInfo:
    """Build a TierInfo object from a tier definition tuple."""
    return TierInfo(
        tier_number=tier_tuple[0],
        tier_name=tier_tuple[1],
        tier_emoji=tier_tuple[2],
        max_bet=tier_tuple[3],
        min_balance=tier_tuple[4],
        max_balance=tier_tuple[5],
        min_xp=tier_tuple[6],
        max_xp=tier_tuple[7],
    )


def get_balance_tier(balance: int) -> TierInfo:
    """Get the tier based on current balance.
    
    Args:
        balance: User's current balance
        
    Returns:
        TierInfo for the appropriate tier
    """
    for tier_data in TIER_DEFINITIONS:
        min_balance = tier_data[4]
        max_balance = tier_data[5]
        
        if max_balance is None:
            # Highest tier
            if balance >= min_balance:
                return _build_tier_info(tier_data)
        else:
            if min_balance <= balance <= max_balance:
                return _build_tier_info(tier_data)
    
    # Default to lowest tier if something goes wrong
    return _build_tier_info(TIER_DEFINITIONS[0])


def get_level_tier(xp: int) -> TierInfo:
    """Get the tier based on experience points.
    
    Args:
        xp: User's total experience points
        
    Returns:
        TierInfo for the appropriate tier
    """
    for tier_data in TIER_DEFINITIONS:
        min_xp = tier_data[6]
        max_xp = tier_data[7]
        
        if max_xp is None:
            # Highest tier
            if xp >= min_xp:
                return _build_tier_info(tier_data)
        else:
            if min_xp <= xp < max_xp:
                return _build_tier_info(tier_data)
    
    # Default to lowest tier if something goes wrong
    return _build_tier_info(TIER_DEFINITIONS[0])


def calculate_level(xp: int) -> int:
    """Calculate level number from experience points.
    
    Args:
        xp: Total experience points
        
    Returns:
        Level number (1-7)
    """
    tier = get_level_tier(xp)
    return tier.tier_number


def get_max_bet_limit(balance: int, xp: int) -> int:
    """Get the maximum bet limit using hybrid approach.
    
    Takes the minimum of balance-based and XP-based limits.
    
    Args:
        balance: User's current balance
        xp: User's experience points
        
    Returns:
        Maximum allowed bet amount
    """
    if not config.ENABLE_BET_LIMITS:
        return 999_999_999  # Unlimited if feature disabled
    
    balance_tier = get_balance_tier(balance)
    level_tier = get_level_tier(xp)
    
    # Return the more restrictive limit
    return min(balance_tier.max_bet, level_tier.max_bet)


def calculate_xp_reward(wager: int) -> int:
    """Calculate XP reward from a wager amount.
    
    Args:
        wager: Amount wagered in the game
        
    Returns:
        XP to award (wager / XP_DIVISOR)
    """
    return wager // config.XP_DIVISOR


def check_tier_up(old_xp: int, new_xp: int) -> bool:
    """Check if a tier-up occurred.
    
    Args:
        old_xp: Previous XP amount
        new_xp: New XP amount
        
    Returns:
        True if the user advanced to a higher tier
    """
    old_tier = get_level_tier(old_xp)
    new_tier = get_level_tier(new_xp)
    return new_tier.tier_number > old_tier.tier_number


def get_next_tier(current_xp: int) -> Optional[TierInfo]:
    """Get the next tier info based on current XP.
    
    Args:
        current_xp: Current experience points
        
    Returns:
        TierInfo for the next tier, or None if at max tier
    """
    current_tier = get_level_tier(current_xp)
    
    # If at max tier, return None
    if current_tier.tier_number >= len(TIER_DEFINITIONS):
        return None
    
    # Return the next tier
    next_tier_data = TIER_DEFINITIONS[current_tier.tier_number]  # 0-indexed
    return _build_tier_info(next_tier_data)


def get_xp_progress(xp: int) -> tuple[int, int, float]:
    """Get XP progress within current tier.
    
    Args:
        xp: Current experience points
        
    Returns:
        Tuple of (current_tier_xp, xp_needed_for_next, progress_percentage)
    """
    current_tier = get_level_tier(xp)
    
    # If at max tier
    if current_tier.max_xp is None:
        return (xp - current_tier.min_xp, 0, 100.0)
    
    xp_in_tier = xp - current_tier.min_xp
    xp_needed = current_tier.max_xp - current_tier.min_xp
    progress = (xp_in_tier / xp_needed) * 100.0 if xp_needed > 0 else 100.0
    
    return (xp_in_tier, xp_needed, progress)


def get_balance_progress(balance: int) -> tuple[int, int, float]:
    """Get balance progress within current tier.
    
    Args:
        balance: Current balance
        
    Returns:
        Tuple of (current_tier_balance, balance_needed_for_next, progress_percentage)
    """
    current_tier = get_balance_tier(balance)
    
    # If at max tier
    if current_tier.max_balance is None:
        return (balance - current_tier.min_balance, 0, 100.0)
    
    balance_in_tier = balance - current_tier.min_balance
    balance_needed = current_tier.max_balance - current_tier.min_balance
    progress = (balance_in_tier / balance_needed) * 100.0 if balance_needed > 0 else 100.0
    
    return (balance_in_tier, balance_needed, progress)


def format_tier_badge(tier: TierInfo) -> str:
    """Format a tier badge for display.
    
    Args:
        tier: TierInfo object
        
    Returns:
        Formatted string like "💎 Diamond"
    """
    return f"{tier.tier_emoji} {tier.tier_name}"

