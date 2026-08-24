from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import GiftKind
from app.models.mixins import TimestampMixin


class GiftSet(TimestampMixin, Base):
    """An admin-curated gift definition offered in the in-app "Подарки"
    section — either a `bundle` (pack + coins, Stars-only, today's original
    gift type) or a `collectible` (a cosmetic image/gif, priced in Stars
    and/or coins — a Telegram-style gift). Players buy one for themselves or
    someone else (bundles disallow buying for yourself; collectibles allow
    it); admins can also hand one out for free (see Gift.is_admin_gift)."""

    __tablename__ = "gift_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    coins_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stars_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[GiftKind] = mapped_column(Enum(GiftKind, name="gift_kind_enum"), nullable=False, default=GiftKind.bundle)
    coins_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_supply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_serial_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    collection_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    pack: Mapped[Optional["Pack"]] = relationship(lazy="joined")
    # ORM-level cascade for the same reason as TrophyDefinition.grants — see
    # that model's comment (SQLite test DB doesn't enforce FK ondelete).
    gifts: Mapped[list["Gift"]] = relationship(back_populates="gift_set", cascade="all, delete-orphan")


class Gift(TimestampMixin, Base):
    """One gift set handed to one recipient — either bought by another
    player (sender_id set, is_admin_gift False) or handed out by an admin
    for free (sender_id None, is_admin_gift True). Sits pending until the
    recipient claims it themselves (claimed_at/pack_opening_id set then),
    mirroring how a purchased pack isn't opened until the player taps it."""

    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gift_set_id: Mapped[int] = mapped_column(ForeignKey("gift_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_admin_gift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    serial_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pack_opening_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pack_openings.id", ondelete="SET NULL"), nullable=True
    )

    gift_set: Mapped["GiftSet"] = relationship(back_populates="gifts", lazy="joined")
    sender: Mapped[Optional["User"]] = relationship(foreign_keys="[Gift.sender_id]", lazy="joined")
