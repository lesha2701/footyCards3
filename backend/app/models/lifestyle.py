from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class LifestyleItem(TimestampMixin, Base):
    """«Имущество» of «Мой игрок»: admin-curated status items (cars, real
    estate, stocks, anything else) bought for coins and/or Telegram Stars.
    Every item adds `prestige` points to the owner's status and may carry
    one admin-set effect (lifestyle_service.EFFECTS): faster freshness
    recovery, an XP bonus or a weekly coin income. One copy per player;
    `max_supply` makes a limited edition (sold_count is bumped under a row
    lock)."""

    __tablename__ = "lifestyle_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # car | estate | stocks | other — see lifestyle_service.CATEGORIES.
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="other", index=True)
    # Shown when there is no uploaded image.
    emoji: Mapped[str] = mapped_column(String(16), nullable=False, default="⭐")
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # 0 = not sold for that currency; at least one of the two must be > 0 to buy.
    coins_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stars_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prestige: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_supply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sold_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # none | freshness_regen | xp_bonus_pct | weekly_income, and its size.
    effect: Mapped[str] = mapped_column(String(24), nullable=False, default="none")
    effect_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserLifestyleItem(Base):
    __tablename__ = "user_lifestyle_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("lifestyle_items.id", ondelete="CASCADE"), nullable=False)
    # coins | stars | admin
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="coins")
    serial_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # weekly_income: paid up to this moment (NULL = since acquired_at).
    income_claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped["LifestyleItem"] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_user_lifestyle_item"),)
