from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import MatchResult, MordoboiMatchStatus, MordoboiOpponentType
from app.models.mixins import utcnow


class MordoboiMatch(Base):
    """One «Мордобой» bout. `user_id` is the side that created it (canonical
    "user" side in server_state), `result` is from that side's point of view
    — same convention as StrategoMatch. Both boxers' secret picks for the
    current exchange live only in server_state and are filtered per viewer
    by mordoboi_service._hydrate_match. `version` grows with every state
    change; clients send it with each pick (stale → 409)."""

    __tablename__ = "mordoboi_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opponent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    opponent_type: Mapped[MordoboiOpponentType] = mapped_column(
        Enum(MordoboiOpponentType, name="mordoboi_opponent_type_enum"), nullable=False
    )
    status: Mapped[MordoboiMatchStatus] = mapped_column(
        Enum(MordoboiMatchStatus, name="mordoboi_match_status_enum"),
        default=MordoboiMatchStatus.pending_accept, nullable=False, index=True,
    )
    result: Mapped[Optional[MatchResult]] = mapped_column(Enum(MatchResult, name="match_result_enum"), nullable=True)
    # ko / points / double_ko / forfeit / timeout
    win_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    user_reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MordoboiQueueEntry(Base):
    """Matchmaking queue row — same lazy "the poller pairs itself" design as
    StrategoQueueEntry."""

    __tablename__ = "mordoboi_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    matched_match_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("mordoboi_matches.id", ondelete="SET NULL"), nullable=True
    )
