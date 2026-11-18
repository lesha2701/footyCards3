from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class LuckyBoardSpin(Base):
    """One spin of «Табло удачи» (lucky_board_service.py). The outcome, the
    reels and everything granted are decided and written in one transaction
    under the user row lock; `prize` is a snapshot of what was granted
    ({"coins", "tokens": [{"skill_code", "quantity"}], "shards",
    "crafted_tokens": [...], "cosmetic_id", "badge_id"}).

    (user_id, idempotency_key) is UNIQUE: a retried spin with the same key
    returns this row instead of spending a second attempt."""

    __tablename__ = "lucky_board_spins"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_lucky_board_spins_user_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # free (daily) / paid (bought for Stars)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # cup / ball / glove / boot / pair / miss (lucky_board_service.OUTCOME_CODES)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reels: Mapped[list] = mapped_column(JSON, nullable=False)
    prize: Mapped[dict] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
