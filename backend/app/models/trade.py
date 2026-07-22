from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
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
