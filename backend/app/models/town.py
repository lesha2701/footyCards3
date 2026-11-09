from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class UserTown(Base):
    """A user's «Город» (services/town_service.py): the rent the houses have
    earned so far. `income_accrued` holds the rent up to `income_since`
    (settled at the old rate before every purchase), capped at
    GameConfig.town_income_max_hours of the current rate."""

    __tablename__ = "user_towns"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    income_accrued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    income_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Opened for coins (GameConfig.town_unlock_coins; free when that is 0).
    unlocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # The player's own name for the town (bought for Stars).
    name: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    # The «Отель»: its rent follows how many cards the player holds.
    hotel_bought_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # The last time the rent was collected — the «care» part of every
    # district's mood (town_service.district_moods).
    cared_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class UserTownHouse(Base):
    """A house the user bought in a district of the town, forever. Unique
    per (user, district, building) — a repeated purchase never charges twice."""

    __tablename__ = "user_town_houses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    district: Mapped[str] = mapped_column(String(16), nullable=False)
    building_code: Mapped[str] = mapped_column(String(24), nullable=False)
    price_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    bought_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "district", "building_code", name="uq_user_town_houses_building"),)


class TownLedger(Base):
    """Every town operation (a house bought, rent collected).
    `(user_id, idempotency_key)` unique — a retried request is replayed,
    never charged or paid twice."""

    __tablename__ = "town_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # buy | hotel | income | unlock | rename | rename_order | resident_sale
    district: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    building_code: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    coins_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coins_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_town_ledger_user_key"),)


class TownResident(TimestampMixin, Base):
    """«Жители города» — the catalog of resident cards (drawn and named by
    the admin, like «Музы»). Every copy a player holds is one inhabitant of
    their town and pays GameConfig.town_resident_rent coins a day; a resident
    with a `bonus` (meant for the legendary ones) also raises the town's
    income once, however many copies (town_service.RESIDENT_BONUSES)."""

    __tablename__ = "town_residents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # One line under the name: «рыбак с Пляжа», «бариста», …
    title: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    icon: Mapped[str] = mapped_column(String(16), default="🧑", nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rarity: Mapped[str] = mapped_column(String(16), default="common", nullable=False)
    bonus: Mapped[str] = mapped_column(String(24), default="none", nullable=False)
    bonus_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Relative weight among residents of the same rarity in a pack slot.
    drop_weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # False = never drops from packs (shop offers, admin grants, events).
    is_pack_droppable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserTownResident(Base):
    """A resident the player owns: one row per (user, resident), a repeat
    drop adds to `copies` — every copy is one more inhabitant."""

    __tablename__ = "user_town_residents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("town_residents.id", ondelete="CASCADE"), nullable=False, index=True)
    copies: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # The district the resident lives in (raises its mood), None = not settled.
    district: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    resident: Mapped[TownResident] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("user_id", "resident_id", name="uq_user_town_residents_user_resident"),)
