from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class DailyReward(Base):
    __tablename__ = "daily_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reward_date: Mapped[date] = mapped_column(Date, nullable=False)
    streak_day: Mapped[int] = mapped_column(Integer, nullable=False)
    coins_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id"), nullable=True)
    random_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_cards.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "reward_date", name="uq_daily_reward_user_date"),)
