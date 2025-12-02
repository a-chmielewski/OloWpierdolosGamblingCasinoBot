"""Bet validation utilities for progressive bet limits."""

from typing import Tuple

from database.models import User
from utils.tier_system import (
    get_max_bet_limit,
    get_balance_tier,
    get_level_tier,
    format_tier_badge,
)
from utils.helpers import format_coins


def validate_bet(user: User, bet_amount: int) -> Tuple[bool, str]:
    """Validate a bet amount against progressive bet limits.
    
    Args:
        user: User object with balance and experience_points
        bet_amount: Amount user wants to bet
        
    Returns:
        Tuple of (is_valid, error_message)
        If valid, error_message is empty string
        If invalid, error_message contains explanation
    """
    from config import config
    
    # Feature flag check
    if not config.ENABLE_BET_LIMITS:
        # No limits if feature is disabled
        if bet_amount <= 0:
            return False, "❌ Bet amount must be positive!"
        if bet_amount > user.balance:
            return False, f"❌ Insufficient balance! You have {format_coins(user.balance)}."
        return True, ""
    
    # Basic validation
    if bet_amount <= 0:
        return False, "❌ Bet amount must be positive!"
    
    if bet_amount > user.balance:
        return False, f"❌ Insufficient balance! You have {format_coins(user.balance)}."
    
    # Check progressive limits
    max_bet = get_max_bet_limit(user.balance, user.experience_points)
    
    if bet_amount > max_bet:
        # Determine which tier is limiting
        balance_tier = get_balance_tier(user.balance)
        level_tier = get_level_tier(user.experience_points)
        
        if balance_tier.max_bet < level_tier.max_bet:
            # Balance is limiting factor
            limiting_tier = balance_tier
            limiting_type = "Balance"
            next_threshold = balance_tier.max_balance
            if next_threshold:
                progress_msg = f"\nReach {format_coins(next_threshold)} balance to unlock the next tier."
            else:
                progress_msg = "\nYou are at the maximum balance tier!"
        else:
            # Level is limiting factor
            limiting_tier = level_tier
            limiting_type = "Level"
            next_threshold = level_tier.max_xp
            if next_threshold:
                xp_needed = next_threshold - user.experience_points
                progress_msg = f"\nGain {xp_needed:,} more XP to unlock the next tier."
            else:
                progress_msg = "\nYou are at the maximum level tier!"
        
        error_msg = (
            f"❌ **Bet Too High**\n\n"
            f"Your {limiting_type} Tier: {format_tier_badge(limiting_tier)}\n"
            f"Maximum allowed bet: {format_coins(max_bet)}\n"
            f"{progress_msg}"
        )
        
        return False, error_msg
    
    # Bet is valid
    return True, ""


def get_max_bet_for_user(user: User) -> int:
    """Get the maximum bet amount for a user.
    
    Args:
        user: User object with balance and experience_points
        
    Returns:
        Maximum bet amount allowed
    """
    return get_max_bet_limit(user.balance, user.experience_points)

