from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import MatchDifficulty, MatchResult, TacticoMatchStatus, TacticoOpponentType
from app.models.mixins import TimestampMixin, utcnow


class TacticoSquad(TimestampMixin, Base):
    __tablename__ = "tactico_squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # 1..5 — mirrors Lineup.template_index (see lineup.py) exactly; one of
    # 5 fixed, always-present saved squads (see
    # tactico_service._ensure_squad_templates).
    template_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Основной состав")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cards: Mapped[list["TacticoSquadCard"]] = relationship(back_populates="squad", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "template_index", name="uq_tactico_squad_user_template"),
        Index(
            "uq_tactico_squad_one_active_per_user", "user_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
    )


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
    # Open (chat-invite) challenges only: coins each side puts up, debited
    # from both at accept time and paid out as a pot at finish (see
    # tactico_service.accept_open_challenge / _finish_match). Always 0 for
    # bot/friend/online matches.
    stake_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
