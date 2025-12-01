"""Shared utilities, locks, and formatters."""

import asyncio
from typing import Dict


class UserLockManager:
    """Manages per-user locks to prevent race conditions."""
    
    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}
    
    def get_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create a lock for a specific user."""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]
    
    def cleanup_unused(self, active_user_ids: set[int]) -> None:
        """Remove locks for users no longer active (optional cleanup)."""
        to_remove = [uid for uid in self._locks if uid not in active_user_ids]
        for uid in to_remove:
            del self._locks[uid]


# Global lock manager instance
_lock_manager = UserLockManager()


def get_user_lock(user_id: int) -> asyncio.Lock:
    """Get the lock for a specific user."""
    return _lock_manager.get_lock(user_id)


def format_coins(amount: int) -> str:
    """Format coin amount with thousands separator and coin emoji."""
    return f"🪙 {amount:,}"


def format_balance_change(amount: int) -> str:
    """Format a balance change with + or - prefix."""
    if amount >= 0:
        return f"+{amount:,}"
    return f"{amount:,}"


class BotException(Exception):
    """Base exception for bot errors."""
    pass


class NotRegisteredException(BotException):
    """User is not registered."""
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"User {user_id} is not registered. Use /register first.")


class InsufficientFundsException(BotException):
    """User doesn't have enough coins."""
    def __init__(self, user_id: int, required: int, available: int):
        self.user_id = user_id
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient funds. Required: {required:,}, Available: {available:,}"
        )


class InvalidBetException(BotException):
    """Invalid bet amount."""
    def __init__(self, message: str):
        super().__init__(message)


class NoActiveGameException(BotException):
    """No active game found."""
    def __init__(self, message: str = "No active game found."):
        super().__init__(message)


class GameAlreadyActiveException(BotException):
    """User already has an active game."""
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"User {user_id} already has an active game.")

