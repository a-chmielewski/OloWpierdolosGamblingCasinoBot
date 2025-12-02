"""Database CRUD operations for Olo Wpierdolo's Gambling Casino Bot."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import config
from database.models import (
    User,
    Transaction,
    TransactionReason,
    GameSession,
    GameType,
    GameStatus,
    DuelParticipant,
)

logger = logging.getLogger(__name__)


# ============================================================================
# User CRUD Operations
# ============================================================================

async def get_user_by_discord_id(
    session: AsyncSession, discord_id: int
) -> Optional[User]:
    """Get a user by their Discord ID."""
    result = await session.execute(
        select(User).where(User.discord_id == discord_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    """Get a user by their database ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    discord_id: int,
    name: str,
    starting_balance: int = config.STARTING_BALANCE,
) -> User:
    """Create a new user with starting balance."""
    user = User(
        discord_id=discord_id,
        name=name,
        balance=starting_balance,
        lifetime_earned=starting_balance,
    )
    session.add(user)
    await session.flush()
    
    # Create initial grant transaction
    transaction = Transaction(
        user_id=user.id,
        amount=starting_balance,
        reason=TransactionReason.INITIAL_GRANT,
    )
    session.add(transaction)
    await session.flush()
    
    logger.info(f"Created new user: {name} (Discord ID: {discord_id})")
    return user


async def get_or_create_user(
    session: AsyncSession, discord_id: int, name: str
) -> Tuple[User, bool]:
    """Get existing user or create new one. Returns (user, created)."""
    user = await get_user_by_discord_id(session, discord_id)
    if user:
        # Update name if changed
        if user.name != name:
            user.name = name
            await session.flush()
        return user, False
    
    user = await create_user(session, discord_id, name)
    return user, True


async def update_user_balance(
    session: AsyncSession,
    user_id: int,
    amount: int,
    reason: TransactionReason,
    game_id: Optional[int] = None,
) -> User:
    """Update user balance and create transaction record."""
    user = await get_user_by_id(session, user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")
    
    user.balance += amount
    
    # Update lifetime stats
    if amount > 0:
        user.lifetime_earned += amount
    else:
        user.lifetime_lost += abs(amount)
    
    # Create transaction record
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        reason=reason,
        ref_game_id=game_id,
    )
    session.add(transaction)
    await session.flush()
    
    logger.debug(f"Updated balance for user {user_id}: {amount:+d} ({reason.value})")
    return user


async def update_last_daily(session: AsyncSession, user_id: int) -> None:
    """Update user's last daily claim timestamp."""
    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    await session.execute(
        update(User).where(User.id == user_id).values(last_daily=now)
    )
    await session.flush()


async def update_last_hourly(session: AsyncSession, user_id: int) -> None:
    """Update user's last hourly claim timestamp."""
    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    await session.execute(
        update(User).where(User.id == user_id).values(last_hourly=now)
    )
    await session.flush()


async def can_claim_daily(session: AsyncSession, user_id: int) -> Tuple[bool, Optional[timedelta]]:
    """
    Check if user can claim daily reward (resets at 3 AM Warsaw time).
    Returns (can_claim, time_remaining).
    """
    user = await get_user_by_id(session, user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")
    
    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    
    # If never claimed, can claim
    if user.last_daily is None:
        return True, None
    
    # Ensure last_daily is timezone-aware
    last_daily = user.last_daily
    if last_daily.tzinfo is None:
        last_daily = last_daily.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    else:
        last_daily = last_daily.astimezone(tz)
    
    # Find today's 3 AM reset time
    today_reset = now.replace(hour=config.DAILY_RESET_HOUR, minute=0, second=0, microsecond=0)
    
    # If it's before 3 AM now, the current reset period started yesterday at 3 AM
    if now < today_reset:
        current_period_start = today_reset - timedelta(days=1)
        next_reset = today_reset
    else:
        # It's after 3 AM now, so current period started today at 3 AM
        current_period_start = today_reset
        next_reset = today_reset + timedelta(days=1)
    
    # Can claim if last claim was before the current period started
    if last_daily < current_period_start:
        return True, None
    
    return False, next_reset - now


async def can_claim_hourly(session: AsyncSession, user_id: int) -> Tuple[bool, Optional[timedelta]]:
    """
    Check if user can claim hourly reward (resets at the top of each hour).
    Returns (can_claim, time_remaining).
    """
    user = await get_user_by_id(session, user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")
    
    tz = ZoneInfo(config.TIMEZONE)
    now = datetime.now(tz)
    
    # If never claimed, can claim
    if user.last_hourly is None:
        return True, None
    
    # Ensure last_hourly is timezone-aware
    last_hourly = user.last_hourly
    if last_hourly.tzinfo is None:
        last_hourly = last_hourly.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    else:
        last_hourly = last_hourly.astimezone(tz)
    
    # Get the start of current hour
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    
    # Next reset is the start of next hour
    next_reset = current_hour_start + timedelta(hours=1)
    
    # Can claim if last claim was before current hour started
    if last_hourly < current_hour_start:
        return True, None
    
    return False, next_reset - now


async def reset_user_balance(
    session: AsyncSession, user_id: int, new_balance: int = config.STARTING_BALANCE
) -> User:
    """Reset user balance to specified amount (admin function)."""
    user = await get_user_by_id(session, user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")
    
    old_balance = user.balance
    adjustment = new_balance - old_balance
    
    user.balance = new_balance
    
    # Create admin adjustment transaction
    transaction = Transaction(
        user_id=user_id,
        amount=adjustment,
        reason=TransactionReason.ADMIN_ADJUSTMENT,
    )
    session.add(transaction)
    await session.flush()
    
    logger.info(f"Admin reset user {user_id} balance from {old_balance} to {new_balance}")
    return user


# ============================================================================
# Leaderboard Queries
# ============================================================================

async def get_richest_users(session: AsyncSession, limit: int = 10) -> List[User]:
    """Get top users by balance."""
    result = await session.execute(
        select(User).order_by(desc(User.balance)).limit(limit)
    )
    return list(result.scalars().all())


async def get_user_rank(session: AsyncSession, user_id: int) -> int:
    """Get user's rank by balance (1-indexed)."""
    user = await get_user_by_id(session, user_id)
    if not user:
        return 0
    
    result = await session.execute(
        select(func.count(User.id)).where(User.balance > user.balance)
    )
    higher_count = result.scalar() or 0
    return higher_count + 1


# ============================================================================
# Game Session CRUD Operations
# ============================================================================

async def create_game_session(
    session: AsyncSession,
    game_type: GameType,
    creator_user_id: int,
    channel_id: int,
    data: Optional[dict] = None,
) -> GameSession:
    """Create a new game session."""
    game = GameSession(
        type=game_type,
        status=GameStatus.PENDING,
        created_by_user_id=creator_user_id,
        channel_id=channel_id,
        data=json.dumps(data) if data else None,
    )
    session.add(game)
    await session.flush()
    
    logger.info(f"Created game session {game.id} of type {game_type.value}")
    return game


async def get_game_session(session: AsyncSession, game_id: int) -> Optional[GameSession]:
    """Get a game session by ID."""
    result = await session.execute(
        select(GameSession).where(GameSession.id == game_id)
    )
    return result.scalar_one_or_none()


async def get_pending_duel_for_user(
    session: AsyncSession, user_id: int
) -> Optional[GameSession]:
    """Get pending duel where user is a participant."""
    result = await session.execute(
        select(GameSession)
        .join(DuelParticipant)
        .where(
            GameSession.type == GameType.DECREASING_DUEL,
            GameSession.status == GameStatus.PENDING,
            DuelParticipant.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_active_game_for_user(
    session: AsyncSession, user_id: int
) -> Optional[GameSession]:
    """Get any active or pending game where user is involved."""
    result = await session.execute(
        select(GameSession)
        .join(DuelParticipant)
        .where(
            DuelParticipant.user_id == user_id,
            GameSession.status.in_([GameStatus.PENDING, GameStatus.ACTIVE]),
        )
    )
    return result.scalar_one_or_none()


async def update_game_status(
    session: AsyncSession, game_id: int, status: GameStatus, data: Optional[dict] = None
) -> GameSession:
    """Update game session status and optionally data."""
    game = await get_game_session(session, game_id)
    if not game:
        raise ValueError(f"Game session {game_id} not found")
    
    game.status = status
    if data is not None:
        game.data = json.dumps(data)
    
    await session.flush()
    return game


async def update_game_message_id(
    session: AsyncSession, game_id: int, message_id: int
) -> None:
    """Update the message ID for a game session."""
    await session.execute(
        update(GameSession).where(GameSession.id == game_id).values(message_id=message_id)
    )
    await session.flush()


# ============================================================================
# Duel Participant CRUD Operations
# ============================================================================

async def add_duel_participant(
    session: AsyncSession,
    game_id: int,
    user_id: int,
    bet_amount: int,
) -> DuelParticipant:
    """Add a participant to a duel."""
    participant = DuelParticipant(
        game_id=game_id,
        user_id=user_id,
        bet_amount=bet_amount,
    )
    session.add(participant)
    await session.flush()
    return participant


async def get_duel_participants(
    session: AsyncSession, game_id: int
) -> List[DuelParticipant]:
    """Get all participants for a game."""
    result = await session.execute(
        select(DuelParticipant).where(DuelParticipant.game_id == game_id)
    )
    return list(result.scalars().all())


async def update_participant_result(
    session: AsyncSession,
    participant_id: int,
    result_value: Optional[int] = None,
    is_winner: Optional[bool] = None,
) -> DuelParticipant:
    """Update participant's result."""
    result = await session.execute(
        select(DuelParticipant).where(DuelParticipant.id == participant_id)
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise ValueError(f"Participant {participant_id} not found")
    
    if result_value is not None:
        participant.result_value = result_value
    if is_winner is not None:
        participant.is_winner = is_winner
    
    await session.flush()
    return participant


# ============================================================================
# Statistics Queries
# ============================================================================

async def get_user_game_stats(
    session: AsyncSession, user_id: int
) -> dict:
    """Get detailed game statistics for a user."""
    # Get duel stats
    duels_played_result = await session.execute(
        select(func.count(DuelParticipant.id))
        .join(GameSession)
        .where(
            DuelParticipant.user_id == user_id,
            GameSession.status == GameStatus.COMPLETED,
        )
    )
    duels_played = duels_played_result.scalar() or 0
    
    duels_won_result = await session.execute(
        select(func.count(DuelParticipant.id))
        .join(GameSession)
        .where(
            DuelParticipant.user_id == user_id,
            DuelParticipant.is_winner == True,
            GameSession.status == GameStatus.COMPLETED,
        )
    )
    duels_won = duels_won_result.scalar() or 0
    
    # Get slots stats
    slots_played_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason.in_([
                TransactionReason.SLOTS_WIN,
                TransactionReason.SLOTS_LOSS,
            ])
        )
    )
    slots_played = slots_played_result.scalar() or 0
    
    slots_won_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason == TransactionReason.SLOTS_WIN,
        )
    )
    slots_won = slots_won_result.scalar() or 0
    
    # Get roulette stats
    roulette_played_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason.in_([
                TransactionReason.ROULETTE_WIN,
                TransactionReason.ROULETTE_LOSS,
            ])
        )
    )
    roulette_played = roulette_played_result.scalar() or 0
    
    roulette_won_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason == TransactionReason.ROULETTE_WIN,
        )
    )
    roulette_won = roulette_won_result.scalar() or 0
    
    # Get group pot stats
    group_pot_played_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason.in_([
                TransactionReason.GROUP_POT_WIN,
                TransactionReason.GROUP_POT_LOSS,
            ])
        )
    )
    group_pot_played = group_pot_played_result.scalar() or 0
    
    group_pot_won_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason == TransactionReason.GROUP_POT_WIN,
        )
    )
    group_pot_won = group_pot_won_result.scalar() or 0
    
    # Get blackjack stats
    blackjack_played_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason.in_([
                TransactionReason.BLACKJACK_WIN,
                TransactionReason.BLACKJACK_LOSS,
            ])
        )
    )
    blackjack_played = blackjack_played_result.scalar() or 0
    
    blackjack_won_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason == TransactionReason.BLACKJACK_WIN,
        )
    )
    blackjack_won = blackjack_won_result.scalar() or 0
    
    # Get animal race stats
    animal_race_played_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason.in_([
                TransactionReason.ANIMAL_RACE_WIN,
                TransactionReason.ANIMAL_RACE_LOSS,
            ])
        )
    )
    animal_race_played = animal_race_played_result.scalar() or 0
    
    animal_race_won_result = await session.execute(
        select(func.count(Transaction.id))
        .where(
            Transaction.user_id == user_id,
            Transaction.reason == TransactionReason.ANIMAL_RACE_WIN,
        )
    )
    animal_race_won = animal_race_won_result.scalar() or 0
    
    # Get biggest win/loss from transactions
    biggest_win_result = await session.execute(
        select(func.max(Transaction.amount))
        .where(
            Transaction.user_id == user_id,
            Transaction.amount > 0,
            Transaction.reason.in_([
                TransactionReason.DUEL_WIN,
                TransactionReason.SLOTS_WIN,
                TransactionReason.ROULETTE_WIN,
                TransactionReason.GROUP_POT_WIN,
                TransactionReason.BLACKJACK_WIN,
                TransactionReason.ANIMAL_RACE_WIN,
            ])
        )
    )
    biggest_win = biggest_win_result.scalar() or 0
    
    biggest_loss_result = await session.execute(
        select(func.min(Transaction.amount))
        .where(
            Transaction.user_id == user_id,
            Transaction.amount < 0,
            Transaction.reason.in_([
                TransactionReason.DUEL_LOSS,
                TransactionReason.SLOTS_LOSS,
                TransactionReason.ROULETTE_LOSS,
                TransactionReason.GROUP_POT_LOSS,
                TransactionReason.BLACKJACK_LOSS,
                TransactionReason.ANIMAL_RACE_LOSS,
            ])
        )
    )
    biggest_loss = biggest_loss_result.scalar() or 0
    
    return {
        "duels_played": duels_played,
        "duels_won": duels_won,
        "duels_lost": duels_played - duels_won,
        "slots_played": slots_played,
        "slots_won": slots_won,
        "slots_lost": slots_played - slots_won,
        "roulette_played": roulette_played,
        "roulette_won": roulette_won,
        "roulette_lost": roulette_played - roulette_won,
        "group_pot_played": group_pot_played,
        "group_pot_won": group_pot_won,
        "group_pot_lost": group_pot_played - group_pot_won,
        "blackjack_played": blackjack_played,
        "blackjack_won": blackjack_won,
        "blackjack_lost": blackjack_played - blackjack_won,
        "animal_race_played": animal_race_played,
        "animal_race_won": animal_race_won,
        "animal_race_lost": animal_race_played - animal_race_won,
        "biggest_win": biggest_win,
        "biggest_loss": abs(biggest_loss),
    }

