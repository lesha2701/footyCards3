from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import MatchResult, StrategoMatchStatus, StrategoOpponentType
from app.models.mixins import utcnow


class StrategoMatch(Base):
    """One «Футбольное Стратего» match. `user_id` is always the side that
    created it (canonical "user" side in server_state, home rows at the
    bottom of the board); `result` is from that side's point of view, same
    convention as TacticoMatch. The full piece layout — including the
    opponent's hidden pieces — lives only in server_state and is filtered
    per viewer by stratego_service._hydrate_match."""

    __tablename__ = "stratego_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opponent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    opponent_type: Mapped[StrategoOpponentType] = mapped_column(
        Enum(StrategoOpponentType, name="stratego_opponent_type_enum"), nullable=False
    )
    status: Mapped[StrategoMatchStatus] = mapped_column(
        Enum(StrategoMatchStatus, name="stratego_match_status_enum"),
        default=StrategoMatchStatus.pending_accept, nullable=False, index=True,
    )
    result: Mapped[Optional[MatchResult]] = mapped_column(Enum(MatchResult, name="match_result_enum"), nullable=True)
    # cup_captured / no_moves / move_limit / forfeit / timeout
    win_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    user_reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class StrategoQueueEntry(Base):
    """Matchmaking queue row — same lazy "the poller pairs itself" design as
    TacticoQueueEntry (see tactico_service.get_search_status)."""

    __tablename__ = "stratego_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    matched_match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stratego_matches.id", ondelete="SET NULL"), nullable=True
    )
