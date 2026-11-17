from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class LoyaltyReward(Base):
    """A one-off loyalty keepsake (services/loyalty_service.py): «Старожил»
    (100 days in the game, alive and active), «Основатель» (among the first
    players) and the «Центурион» card owed to whoever reached 100 days in a
    row before it existed. Unique on user + code = granted once; `seen_at`
    is set when the popup was shown."""

    __tablename__ = "loyalty_rewards"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_loyalty_rewards_user_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    rewards: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
