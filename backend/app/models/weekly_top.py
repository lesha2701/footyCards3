from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class WeeklyTopRun(Base):
    """«Топ недели» settled for one week — the primary key is what makes the
    settlement run once even when the bot's sweep and a player's request
    race for it (weekly_top_service.settle)."""

    __tablename__ = "weekly_top_runs"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    winners: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WeeklyTopAward(Base):
    """One place in one ranking's weekly top: what was granted (a snapshot,
    so later admin edits don't rewrite history) and whether the player has
    seen the popup yet."""

    __tablename__ = "weekly_top_awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # {"coins", "pack_name", "cards", "cosmetic_name", "cosmetic_style"}
    rewards: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("week_start", "metric", "rank", name="uq_weekly_top_awards_place"),
        Index("ix_weekly_top_awards_user_seen", "user_id", "seen_at"),
    )
