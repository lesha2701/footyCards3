from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ComebackGift(Base):
    """«Подарок за возвращение» (services/comeback_gift_service.py): one row
    per gift, the newest one drives the cooldown; `seen_at` is set when the
    popup was shown."""

    __tablename__ = "comeback_gifts"
    __table_args__ = (UniqueConstraint("user_id", "gift_date", name="uq_comeback_gifts_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    gift_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_away: Mapped[int] = mapped_column(Integer, nullable=False)
    # What was granted (GrantedRewardsOut) — the popup shows it.
    rewards: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
