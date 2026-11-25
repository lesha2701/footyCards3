from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProfileRespect(Base):
    """«👍 Респект» on someone's profile: one per giver, target and day
    (the unique constraint is the guarantee)."""

    __tablename__ = "profile_respects"
    __table_args__ = (UniqueConstraint("giver_id", "target_id", "day", name="uq_profile_respect_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    giver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
