from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import GameSessionStatus, GameType
from app.models.mixins import utcnow


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    game_type: Mapped[GameType] = mapped_column(Enum(GameType, name="game_type_enum"), nullable=False)
    status: Mapped[GameSessionStatus] = mapped_column(
        Enum(GameSessionStatus, name="game_session_status_enum"), default=GameSessionStatus.in_progress, nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_rewarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    rounds: Mapped[list["MemoryGameRound"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class MemoryGameRound(Base):
    __tablename__ = "memory_game_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[str] = mapped_column(String(256), nullable=False)
    was_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped["GameSession"] = relationship(back_populates="rounds")
