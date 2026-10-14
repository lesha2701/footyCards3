from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class MagnateMatch(Base):
    """One «Футбольный магнат» table for up to 4 seats.

    mode: bot (1 human + 3 bots) / public (matchmaking lobby, empty seats
    filled by bots when the lobby timer runs out) / private (room joined by
    invite_code). status: lobby → in_progress → finished, or cancelled.

    The whole game lives in server_state (see magnate_engine); `version`
    goes up on every change so a client action can be rejected when it was
    made against an outdated screen, and next_deadline_at (lobby timer, turn
    timer or the overall time limit, whichever is first) is what the sweep
    — lazy on reads and the bot's background loop — looks at."""

    __tablename__ = "magnate_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="lobby", nullable=False, index=True)
    creator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invite_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, unique=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    next_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    finish_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MagnateSeat(Base):
    """A seat at a table. user_id NULL = a bot seat. A human who left or
    timed out too often keeps the row (`replaced_by_bot`) — the bot plays
    on in their place and they get no reward. Unique (match, seat) and
    (match, user) make concurrent joins safe."""

    __tablename__ = "magnate_seats"
    __table_args__ = (
        UniqueConstraint("match_id", "seat", name="uq_magnate_seats_match_seat"),
        UniqueConstraint("match_id", "user_id", name="uq_magnate_seats_match_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("magnate_matches.id", ondelete="CASCADE"), nullable=False, index=True)
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    replaced_by_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    place: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
