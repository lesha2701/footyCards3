"""Club emblem constructor and «Казна за Stars».

The emblem itself (pattern, second colour, symbol, letters, outline, effect)
lives on `Club` columns; what a club may put on it is `ClubEmblemUnlock`
rows over the admin-priced `ClubEmblemItem` catalog (see
club_emblem_service). `ClubDonation` is one Stars top-up of a club budget —
the «Доска меценатов» and the members' sponsor badges are sums over it."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ClubEmblemItem(Base):
    __tablename__ = "club_emblem_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "color2" | "pattern" | "letters" | "symbol" | "outline" | "effect"
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # What the frontend draws (lib/clubEmblem.ts); fixed per kind, not admin-editable.
    style_key: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Exactly one of the two is > 0 for a sellable item; coins come from the club budget.
    coins_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("kind", "style_key", name="uq_club_emblem_items_kind_style"),)


class ClubEmblemUnlock(Base):
    __tablename__ = "club_emblem_unlocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("club_emblem_items.id", ondelete="CASCADE"), nullable=False)
    # "coins" | "stars" | "admin"
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("club_id", "item_id", name="uq_club_emblem_unlocks_club_item"),)


class ClubDonation(Base):
    __tablename__ = "club_donations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, nullable=False)
    # One donation per paid invoice — what makes a redelivered payment a no-op.
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("stars_invoices.id", ondelete="CASCADE"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("invoice_id", name="uq_club_donations_invoice_id"),)
