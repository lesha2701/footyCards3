from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import MatchDifficulty, MatchResult, TacticoMatchStatus, TacticoOpponentType
from app.models.mixins import TimestampMixin, utcnow


class TacticoSquad(TimestampMixin, Base):
    __tablename__ = "tactico_squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    cards: Mapped[list["TacticoSquadCard"]] = relationship(back_populates="squad", cascade="all, delete-orphan")


class TacticoSquadCard(Base):
    __tablename__ = "tactico_squad_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("tactico_squads.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[int] = mapped_column(
        ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )

    squad: Mapped["TacticoSquad"] = relationship(back_populates="cards")

    __table_args__ = (UniqueConstraint("squad_id", "user_card_id", name="uq_tactico_squad_card"),)


class TacticoMatch(Base):
    __tablename__ = "tactico_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    opponent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    opponent_type: Mapped[TacticoOpponentType] = mapped_column(
        Enum(TacticoOpponentType, name="tactico_opponent_type_enum"), nullable=False
    )
    difficulty: Mapped[Optional[MatchDifficulty]] = mapped_column(
        Enum(MatchDifficulty, name="match_difficulty_enum"), nullable=True
    )
    status: Mapped[TacticoMatchStatus] = mapped_column(
        Enum(TacticoMatchStatus, name="tactico_match_status_enum"),
        default=TacticoMatchStatus.pending_accept, nullable=False, index=True,
    )
    user_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[Optional[MatchResult]] = mapped_column(Enum(MatchResult, name="match_result_enum"), nullable=True)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TacticoQueueEntry(Base):
    """One player currently searching for an opponent via matchmaking.
    `matched_match_id` is set by whichever poll (theirs or the paired
    player's) performs the pairing — see wheel_service.py-style "the reader
    does the lazy work" pattern, applied here to matchmaking instead of
    round timeouts (see tactico_service.get_search_status)."""

    __tablename__ = "tactico_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    matched_match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tactico_matches.id", ondelete="SET NULL"), nullable=True
    )
