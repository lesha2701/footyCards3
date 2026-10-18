from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.enums import TradeCardSide, TradeStatus
from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class TradeOffer(TimestampMixin, Base):
    __tablename__ = "trade_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus, name="trade_status_enum"), default=TradeStatus.pending, nullable=False, index=True
    )
    sender_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    receiver_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    cards: Mapped[list["TradeOfferCard"]] = relationship(back_populates="offer", cascade="all, delete-orphan")


class TradeOfferCard(Base):
    __tablename__ = "trade_offer_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_offer_id: Mapped[int] = mapped_column(
        ForeignKey("trade_offers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_card_id: Mapped[int] = mapped_column(
        ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    side: Mapped[TradeCardSide] = mapped_column(Enum(TradeCardSide, name="trade_card_side_enum"), nullable=False)

    offer: Mapped["TradeOffer"] = relationship(back_populates="cards")


class TradeWish(Base):
    """«Поиск обменов»: a player the user is looking for (kind="want") or is
    ready to give away (kind="give"). Matching reads live card ownership, so
    a wish never reserves or locks anything (services/trade_finder_service.py)."""

    __tablename__ = "trade_wishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    # «Ищу»: last «у игрока появилась карточка» notification, for the cooldown.
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "player_id", "kind", name="uq_trade_wishes_user_player_kind"),
        Index("ix_trade_wishes_player_kind", "player_id", "kind"),
    )
