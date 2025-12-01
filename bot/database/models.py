"""SQLAlchemy models for Olo Wpierdolo's Gambling Casino Bot."""

import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class TransactionReason(enum.Enum):
    """Reasons for balance changes."""
    INITIAL_GRANT = "initial_grant"
    DAILY_REWARD = "daily_reward"
    DUEL_WIN = "duel_win"
    DUEL_LOSS = "duel_loss"
    SLOTS_WIN = "slots_win"
    SLOTS_LOSS = "slots_loss"
    ROULETTE_WIN = "roulette_win"
    ROULETTE_LOSS = "roulette_loss"
    GROUP_POT_WIN = "group_pot_win"
    GROUP_POT_LOSS = "group_pot_loss"
    ADMIN_ADJUSTMENT = "admin_adjustment"
    TRANSFER_SENT = "transfer_sent"
    TRANSFER_RECEIVED = "transfer_received"


class GameType(enum.Enum):
    """Types of games."""
    DECREASING_DUEL = "decreasing_duel"
    SLOTS = "slots"
    ROULETTE = "roulette"
    GROUP_POT = "group_pot"


class GameStatus(enum.Enum):
    """Status of a game session."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class User(Base):
    """Represents a Discord user in the bot's economy."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_daily: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Relationships
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="user", lazy="selectin"
    )
    created_games: Mapped[List["GameSession"]] = relationship(
        "GameSession", back_populates="creator", lazy="selectin"
    )
    game_participations: Mapped[List["DuelParticipant"]] = relationship(
        "DuelParticipant", back_populates="user", lazy="selectin"
    )
    
    @property
    def net_profit(self) -> int:
        """Calculate net profit (lifetime earned - lifetime lost)."""
        return self.lifetime_earned - self.lifetime_lost
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, discord_id={self.discord_id}, name={self.name}, balance={self.balance})>"


class Transaction(Base):
    """Record of all balance changes."""
    
    __tablename__ = "transactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[TransactionReason] = mapped_column(
        Enum(TransactionReason), nullable=False
    )
    ref_game_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("game_sessions.id"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    game_session: Mapped[Optional["GameSession"]] = relationship(
        "GameSession", back_populates="transactions"
    )
    
    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, reason={self.reason.value})>"


class GameSession(Base):
    """Generic game session for multi-step games."""
    
    __tablename__ = "game_sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[GameType] = mapped_column(Enum(GameType), nullable=False)
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus), default=GameStatus.PENDING, nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string for game state
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Relationships
    creator: Mapped["User"] = relationship("User", back_populates="created_games")
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="game_session"
    )
    participants: Mapped[List["DuelParticipant"]] = relationship(
        "DuelParticipant", back_populates="game_session", lazy="selectin"
    )
    
    def __repr__(self) -> str:
        return f"<GameSession(id={self.id}, type={self.type.value}, status={self.status.value})>"


class DuelParticipant(Base):
    """Participant in a duel or group game."""
    
    __tablename__ = "duel_participants"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    bet_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    result_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_winner: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Relationships
    game_session: Mapped["GameSession"] = relationship(
        "GameSession", back_populates="participants"
    )
    user: Mapped["User"] = relationship("User", back_populates="game_participations")
    
    def __repr__(self) -> str:
        return f"<DuelParticipant(id={self.id}, game_id={self.game_id}, user_id={self.user_id}, bet={self.bet_amount})>"

