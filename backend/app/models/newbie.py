from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class NewbieProgress(Base):
    """«Путь дебютанта» of one player (newbie_service): the first pack, the
    team pack, the first Arena match, «попробуй режим» tasks and the day-2 /
    day-3 gifts. `claimed` maps a step code to when it was done/claimed —
    also the funnel the admin analytics read."""

    __tablename__ = "newbie_progress"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    # Local calendar day the path started — day 2 / day 3 gifts count from it.
    start_day: Mapped[date] = mapped_column(Date, nullable=False)
    claimed: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # The last day (2 or 3) the bot reminded about that day's gift.
    reminded_day: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Kept for future step counters without a migration.
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
