from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Rarity, WheelPrizeType, WheelSpinSource
from app.models.mixins import TimestampMixin, utcnow
from sqlalchemy import Enum as SAEnum


class WheelPrize(TimestampMixin, Base):
    """One admin-configured entry in the wheel's prize pool. Selected by
    weighted random pick (see wheel_service._roll_prize) — weight is a plain
    relative number, not a normalized probability, so an admin can add or
    remove entries without rebalancing everything else to sum to 1.

    Exactly one of coins_amount/pack_id/card_rarity/badge_id is set,
    matching prize_type — enforced at the application layer (schemas +
    service), not a DB constraint, mirroring how Pack/GiftSet handle their
    own similarly-shaped "one of several optional fields" data.
    """

    __tablename__ = "wheel_prizes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prize_type: Mapped[WheelPrizeType] = mapped_column(SAEnum(WheelPrizeType, name="wheel_prize_type_enum"), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    coins_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="CASCADE"), nullable=True)
    card_rarity: Mapped[Optional[Rarity]] = mapped_column(SAEnum(Rarity, name="rarity_enum"), nullable=True)
    badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="CASCADE"), nullable=True)

    pack: Mapped[Optional["Pack"]] = relationship(lazy="joined")
    badge: Mapped[Optional["Badge"]] = relationship(lazy="joined")


class WheelSpin(Base):
    """One row per spin, regardless of payment path — the durable "receipt"
    for what was won, filling the same role PackOpening/Gift play for their
    reward types. Needed so a Stars-paid spin's invoice-status poll
    (StarsInvoiceStatusOut) can reconstruct "what did this delivered
    invoice actually grant" after the fact (see
    stars_payment_service._delivered_result)."""

    __tablename__ = "wheel_spins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    prize_id: Mapped[int] = mapped_column(ForeignKey("wheel_prizes.id", ondelete="RESTRICT"), nullable=False)
    source: Mapped[WheelSpinSource] = mapped_column(SAEnum(WheelSpinSource, name="wheel_spin_source_enum"), nullable=False)

    pack_opening_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pack_openings.id", ondelete="SET NULL"), nullable=True)
    user_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True)
    badge_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_badge_coins: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    coins_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    prize: Mapped["WheelPrize"] = relationship(lazy="joined")
