from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    # Gifts guests left (town_social_service.gift): paid with the next rent
    # collection, on top of it.
    gifts_pending: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    # «Набор жителей»: residents with the same set_name form a set; holding
    # every active one gives the town town_mood.set_rent_pct (town_service.resident_sets).
    set_name: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
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


class UserTownQuest(Base):
    """A daily «Задание жителя» (town_social_service): one of
    GameConfig.town_social.quests_per_day, unique per (user, day, slot).
    `baseline` is the counter when it was given (games played so far) —
    progress is the counter now minus it."""

    __tablename__ = "user_town_quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("town_residents.id", ondelete="SET NULL"), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "day", "slot", name="uq_user_town_quest_slot"),)


class TownVisit(Base):
    """A guest in someone's town on a day: one row per (visitor, owner, day),
    with the like and the gift the guest left (town_social_service)."""

    __tablename__ = "town_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visitor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    liked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gift_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("visitor_id", "owner_id", "day", name="uq_town_visit_day"),)


class UserTownSeasonItem(Base):
    """«Сезонный город»: a limited decoration bought for Stars
    (town_season_service.ITEMS), numbered per item."""

    __tablename__ = "user_town_season_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False)
    serial: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "code", name="uq_town_season_item_user"),
        UniqueConstraint("code", "serial", name="uq_town_season_item_serial"),
    )


class TownWeek(Base):
    """«Город недели» settled for a week (ISO "2026-W46"): the row is the
    lock — a week is paid once, whoever reads the ranking first."""

    __tablename__ = "town_weeks"

    week: Mapped[str] = mapped_column(String(10), primary_key=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TownWeekResult(Base):
    """A rewarded place of «Город недели»."""

    __tablename__ = "town_week_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    place: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("week", "place", name="uq_town_week_place"),
        UniqueConstraint("week", "user_id", name="uq_town_week_user"),
    )
