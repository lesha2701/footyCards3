from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserDailyActivity(Base):
    """One row per user per local calendar day (settings.timezone) on which
    the user made at least one authenticated request — the history behind
    the admin analytics (DAU, retention cohorts, the new-player funnel).

    `users.last_seen_at` only keeps the latest visit, so without this table
    "did this player come back on day 7" can't be answered. Written once per
    day from the same spot that advances the daily login streak
    (core/dependencies.py); the composite primary key makes a concurrent
    second write a no-op instead of a duplicate. Rows before this table
    existed were backfilled from timestamped activity (migration 0150) and
    are therefore a lower bound, not exact."""

    __tablename__ = "user_daily_activity"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)

    __table_args__ = (Index("ix_user_daily_activity_day", "day"),)


class SectionTimeDaily(Base):
    """Seconds a player actively spent in one section of the Mini App on one
    local day (settings.timezone): the «Где проводят время» admin report.

    The app counts time only while its page is visible and the player did
    something in the last minute, and sends what it counted once a minute
    (`POST /activity/time`, section_time_service); each batch adds to the
    row, so one row per (day, section, user) whatever the visits."""

    __tablename__ = "section_time_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    section: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_section_time_daily_user", "user_id"),)
