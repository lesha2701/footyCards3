from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ClubWarRound(Base):
    """One per league week once its «Клубные войны» have been paired. The
    primary key is the idempotency guarantee: two concurrent matchmakings of
    the same week race on this insert and the loser rolls back
    (club_war_service.start_due)."""

    __tablename__ = "club_war_rounds"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClubWar(Base):
    """Two clubs paired by war rating for one 48-hour window: their members'
    activity in the window scores war points (club_war_service)."""

    __tablename__ = "club_wars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(ForeignKey("club_war_rounds.week_start", ondelete="CASCADE"), nullable=False)
    club_a_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    club_b_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # "active" | "finished"
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    score_a: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score_b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Null on a draw (or while active).
    winner_club_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("week_start", "club_a_id", name="uq_club_war_week_club_a"),
        UniqueConstraint("week_start", "club_b_id", name="uq_club_war_week_club_b"),
        Index("ix_club_wars_status_ends_at", "status", "ends_at"),
    )
