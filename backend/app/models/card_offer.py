from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class CardOffer(TimestampMixin, Base):
    """«Карты за звёзды»: one footballer card sold in the shop for Telegram
    Stars, set up by the admin — e.g. a retired / limited card
    (Player.is_pack_droppable = False) back for a short window. Optional
    window (starts_at / ends_at), stock (copies in total) and a per-player
    limit; sold_count grows on delivery (card_offer_service)."""

    __tablename__ = "card_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    stars_price: Mapped[int] = mapped_column(Integer, nullable=False)
    # Shown on the tile, e.g. «Переиздание легенды» (optional).
    title: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stock: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = unlimited
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 0 = unlimited
    sold_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # When «Разослать игрокам» went out (once per offer).
    announced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the «осталось 3 часа» reminder went out (once per offer).
    reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    player = relationship("Player", lazy="joined")


class CardOfferView(Base):
    """A player opened «Карты ⭐» while this offer was on sale — who gets
    the reminder before it ends (unless they bought it)."""

    __tablename__ = "card_offer_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("card_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("offer_id", "user_id", name="uq_card_offer_views_offer_user"),)


class CardOfferPurchase(Base):
    """One delivered purchase — unique per Stars invoice, which is what
    makes a redelivery a no-op; also what the per-player limit counts."""

    __tablename__ = "card_offer_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("card_offers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("stars_invoices.id", ondelete="CASCADE"), nullable=False)
    user_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True)
    stars_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("invoice_id", name="uq_card_offer_purchases_invoice"),)
