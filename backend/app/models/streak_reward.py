from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class StreakReward(Base):
    """A keepsake for N days in a row in the game (GameConfig.streak_rewards,
    services/streak_reward_service.py): granted once per player per
    milestone; `seen_at` is set when the popup was shown."""

    __tablename__ = "streak_rewards"
    __table_args__ = (UniqueConstraint("user_id", "days", name="uq_streak_rewards_user_days"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    # What was granted (GrantedRewardsOut) — the popup shows it.
    rewards: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
