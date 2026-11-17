from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class AnniversaryMember(Base):
    """«💯 Нам 100 дней!»: one row per player per event (`event_key`, e.g.
    "100days-2026") — his share of the community goal «Сотня» (rewarded
    games played during the event) and how far he got in the gift calendar.
    The community total is a SUM over these rows, never a shared counter.
    Mutated only under the user's row lock."""

    __tablename__ = "anniversary_members"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    games: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calendar_claimed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    calendar_last_day: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnniversaryClaim(Base):
    """Every reward taken: a calendar day, a community tier, the recap gift.
    `ref_key` is unique per player — a retried claim pays once."""

    __tablename__ = "anniversary_claims"
    __table_args__ = (UniqueConstraint("user_id", "ref_key", name="uq_anniversary_claims_user_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # calendar / community / recap
    ref_key: Mapped[str] = mapped_column(String(96), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
