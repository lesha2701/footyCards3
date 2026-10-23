"""«Экипировка»: things a player's card wears (services/equipment_service.py).

  * EquipmentCollection — a themed line of things («Ретро-70»); wearing
    `set_size` things of one collection on one card adds `set_bonus_rating`.
  * EquipmentItem — the admin-editable catalog: slot, rarity, one effect,
    optional club/country condition, coin and Stars prices, photo.
  * UserEquipment — one owned copy of a thing («Инвентарь»). `user_card_id`
    set = worn by that card in `slot` (one thing per slot per card, unique).
    The copy always stays with its owner: selling/burning the card frees it
    (FK SET NULL), a trade takes it off before the card changes hands.

What a card wears is summed into UserCard.equipment_* when it changes, so
every game mode reads it off the card row like the diamond/star bonuses.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class EquipmentCollection(TimestampMixin, Base):
    __tablename__ = "equipment_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Things of this collection worn by ONE card needed for the set bonus.
    set_size: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    set_bonus_rating: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # «Комплект сборной»: the full set on one card also gives +N chemistry to
    # every on-position player of this country in that card's squad
    # (chemistry_service). NULL = no team bonus.
    set_team_country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    set_team_chemistry: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EquipmentItem(TimestampMixin, Base):
    __tablename__ = "equipment_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    icon: Mapped[str] = mapped_column(String(16), default="👕", nullable=False)
    # boots | kit | socks | gloves | accessory | artifact (equipment_service.SLOTS)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    rarity: Mapped[str] = mapped_column(String(16), default="common", nullable=False)
    collection_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("equipment_collections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # equipment_service.EFFECTS: rating | shot_pp | dribble_pp | save_pp |
    # tackle_pp | pass_pp | chemistry | xp_pct | coins_pct
    effect: Mapped[str] = mapped_column(String(16), default="rating", nullable=False)
    effect_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Effect only for a player of this club / country (NULL = anyone):
    # «родная форма», national-team kits.
    cond_club: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cond_country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # 0 = not sold for that currency.
    coins_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Limited edition: at most max_supply copies ever sold (NULL = unlimited);
    # sold_count is also the next copy's serial number.
    max_supply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sold_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Seasonal: on sale only inside this window (either end NULL = open).
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    collection: Mapped[Optional["EquipmentCollection"]] = relationship(lazy="joined")


class UserEquipment(Base):
    __tablename__ = "user_equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("equipment_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The item's slot, copied at equip time (the unique key below needs it).
    slot: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # coins | stars | admin
    # «№7 из 50»: the item's sale order (copies sold before serials existed: NULL).
    serial_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Coin purchases: a retried request with the same key is a no-op.
    purchase_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    item: Mapped["EquipmentItem"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_card_id", "slot", name="uq_user_equipment_card_slot"),
        UniqueConstraint("user_id", "purchase_key", name="uq_user_equipment_purchase_key"),
    )
