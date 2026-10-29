from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class AuctionLot(Base):
    """«Трансферный рынок»: one specific copy (UserCard row) put up for sale.

    status: active → sold (bids or «купить сейчас») / expired (no bids) /
    cancelled (seller, only while there are no bids) / removed (admin).
    While active the card is held with `is_locked_in_trade` (the flag every
    lineup / squad / trade / sell / upgrade check already honours), and the
    leading bid's coins are held off the bidder's balance (escrow). The
    partial unique index keeps a copy in at most one active lot.

    fee_pct is frozen at listing time, so an admin retune never changes the
    terms of a lot that is already running."""

    __tablename__ = "auction_lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    # Denormalized from the card for search (the card can't change while listed).
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    start_price: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_now_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_bid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_bidder_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bid_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fee_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    winner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    final_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fee_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    close_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index(
            "uq_auction_lots_active_card", "user_card_id", unique=True,
            postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'"),
        ),
        CheckConstraint("start_price > 0", name="ck_auction_lots_start_price"),
        CheckConstraint(
            "buy_now_price IS NULL OR buy_now_price > start_price", name="ck_auction_lots_buy_now_price",
        ),
    )


class AuctionBid(Base):
    """Every accepted bid (and the «купить сейчас» purchase, kind=buy_now).

    (lot_id, amount) is unique — bids only go up, so two racing requests can
    never both be accepted at the same price — and (bidder_id,
    idempotency_key) makes a retried bid request a replay instead of a
    second escrow. status: leading → outbid (refunded) / won / refunded
    (lot removed by an admin)."""

    __tablename__ = "auction_bids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("auction_lots.id", ondelete="CASCADE"), nullable=False, index=True)
    bidder_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="bid", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="leading", nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("lot_id", "amount", name="uq_auction_bids_lot_amount"),
        UniqueConstraint("bidder_id", "idempotency_key", name="uq_auction_bids_idempotency"),
        CheckConstraint("amount > 0", name="ck_auction_bids_amount"),
    )


class AgentLicense(Base):
    """«Агентская лицензия»: only its holders may put lots on the market
    (bidding and buying are open to everyone). Bought for Stars
    (shop product "agent_license", agent_license_service); every purchase
    extends expires_at by GameConfig.agent_license_days from max(now,
    expires_at). One row per user. revoked_at set by an admin (e.g. after a
    manual Stars refund) ends it at once; a later purchase starts it again."""

    __tablename__ = "agent_licenses"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    first_bought_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_bought_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    purchases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
