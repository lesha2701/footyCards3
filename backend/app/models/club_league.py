from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ClubLeagueWeek(Base):
    """One row per settled "Лига клубов" week. The primary key is the
    idempotency guarantee: two concurrent settlements of the same week race
    on this insert and the loser rolls back (club_league_service.settle_due).
    `is_bootstrap` marks the very first row, written without paying anything
    so activity from before the league existed is never rewarded."""

    __tablename__ = "club_league_weeks"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    is_bootstrap: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClubLeagueResult(Base):
    __tablename__ = "club_league_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(
        ForeignKey("club_league_weeks.week_start", ondelete="CASCADE"), nullable=False, index=True
    )
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("week_start", "club_id", name="uq_club_league_result_week_club"),)
