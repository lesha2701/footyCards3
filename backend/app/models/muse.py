"""«Музы»: companions of the player's own footballer («Мой футболист»),
see services/muse_service.py.

  * MuseCollection — a themed line of Muses (admin-editable, photo).
  * Muse — the catalog: rarity, one bonus (`effect`/`effect_value`), drop
    weight in the «Музы» pack, photo or emoji placeholder.
  * UserMuse — a Muse the player owns: one row per (user, muse); a repeat
    drop adds to `copies` (spares sell for coins). `is_active` marks the one
    Muse that inspires «Мой футболист» (at most one per user, partial unique
    index).
  * MuseAccessory — gifts for a Muse (bag, dress, cosmetics, …): each raises
    the Muse's bonus by `boost_pct` percent. Bought for coins or Stars.
  * UserMuseAccessory — a gift bought for one owned Muse; it stays hers.
  * MuseDailyClaim — the once-a-day «daily_coins» bonus, one row per user
    per local day (the unique key is the idempotency guarantee).
  * MuseDate — «Свидание»: once a local day a random mini-game played with
    the Muse on an extra attempt; finishing it (any result) pays
    `muse_date_coins` and inspires her for `muse_inspiration_hours`.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class MuseCollection(TimestampMixin, Base):
    __tablename__ = "muse_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Muse(TimestampMixin, Base):
    __tablename__ = "muses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("muse_collections.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # One line under the name: «модель из Милана», «теннисистка», …
    title: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    icon: Mapped[str] = mapped_column(String(16), default="💃", nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rarity: Mapped[str] = mapped_column(String(16), default="common", nullable=False)
    effect: Mapped[str] = mapped_column(String(24), default="daily_coins", nullable=False)
    effect_value: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # Relative weight among Muses of the same rarity in a pack slot.
    drop_weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    collection: Mapped[Optional[MuseCollection]] = relationship(lazy="joined")


class UserMuse(Base):
    __tablename__ = "user_muses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    muse_id: Mapped[int] = mapped_column(ForeignKey("muses.id", ondelete="CASCADE"), nullable=False, index=True)
    copies: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    muse: Mapped[Muse] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "muse_id", name="uq_user_muses_user_muse"),
        Index(
            "uq_user_muses_one_active", "user_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active = 1"),
        ),
    )


class MuseAccessory(TimestampMixin, Base):
    __tablename__ = "muse_accessories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    icon: Mapped[str] = mapped_column(String(16), default="👜", nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # bag | dress | swimsuit | cosmetics | jewelry | shoes | perfume | other (muse_service.KINDS).
    kind: Mapped[str] = mapped_column(String(16), default="other", nullable=False)
    rarity: Mapped[str] = mapped_column(String(16), default="common", nullable=False)
    # +N% to the bonus of the Muse it is given to.
    boost_pct: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    coins_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserMuseAccessory(Base):
    __tablename__ = "user_muse_accessories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_muse_id: Mapped[int] = mapped_column(ForeignKey("user_muses.id", ondelete="CASCADE"), nullable=False, index=True)
    accessory_id: Mapped[int] = mapped_column(ForeignKey("muse_accessories.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    purchase_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    accessory: Mapped[MuseAccessory] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_muse_id", "accessory_id", name="uq_user_muse_accessories_once"),
        UniqueConstraint("user_id", "purchase_key", name="uq_user_muse_accessories_purchase_key"),
    )


class MuseDailyClaim(Base):
    __tablename__ = "muse_daily_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    claim_date: Mapped[date] = mapped_column(Date, nullable=False)
    muse_id: Mapped[Optional[int]] = mapped_column(ForeignKey("muses.id", ondelete="SET NULL"), nullable=True)
    coins: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "claim_date", name="uq_muse_daily_claims_user_day"),)


class MuseDate(Base):
    __tablename__ = "muse_dates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date_day: Mapped[date] = mapped_column(Date, nullable=False)
    # memory | pairs | hangman (muse_service.DATE_GAMES)
    game: Mapped[str] = mapped_column(String(16), nullable=False)
    muse_id: Mapped[Optional[int]] = mapped_column(ForeignKey("muses.id", ondelete="SET NULL"), nullable=True)
    # The game session played on this date (the latest one if restarted).
    session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "date_day", name="uq_muse_dates_user_day"),)
