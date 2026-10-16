from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

RECEIPT_STATUSES = ("pending", "delivered", "failed", "refunded")


class StarsPaymentReceipt(TimestampMixin, Base):
    """Every Telegram Stars `successful_payment` the bot has received — the
    durable record that the player was actually charged.

    Telegram charges the player *before* we deliver anything, so a delivery
    that fails (backend down, timeout, a product an admin switched off
    mid-checkout) must never just vanish into a log line. The bot inserts
    this row first (straight into Postgres, so it survives even when the
    backend is unreachable), then asks the backend to deliver; the backend
    keeps `status` up to date (stars_receipt_service). Failed rows are
    retried automatically with backoff by the bot and listed in the admin
    panel with «начислить ещё раз» / «вернуть звёзды».

    status: pending (recorded, not delivered yet) → delivered | failed
    (will be retried) | refunded (Stars returned; never delivered after)."""

    __tablename__ = "stars_payment_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    payload_token: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'delivered', 'failed', 'refunded')", name="ck_stars_payment_receipts_status"
        ),
        Index("ix_stars_payment_receipts_retry", "status", "next_attempt_at"),
    )
