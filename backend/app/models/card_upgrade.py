from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import Rarity
from app.models.mixins import TimestampMixin


class CardUpgradeRule(TimestampMixin, Base):
    """Admin-tunable odds/cost for risking a card at `from_rarity` to try to
    turn it into a random card at `to_rarity`. Exactly one row per valid
    (from, to) pair with from < to in RARITY_ORDER."""

    __tablename__ = "card_upgrade_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False)
    to_rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False)
    success_chance: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    coin_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Staking N same-rarity cards in one attempt (instead of just 1) adds
    # this much success chance per extra card, capped at max_success_chance
    # — 0 by default, a no-op until an admin opts a rule into the mechanic.
    extra_card_bonus: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    max_success_chance: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)

    __table_args__ = (UniqueConstraint("from_rarity", "to_rarity", name="uq_card_upgrade_rule"),)


class CardUpgradeAttempt(Base):
    """Audit trail + idempotency guard for upgrade attempts. The staked card
    is deleted from user_cards regardless of outcome, so this is the only
    record of what the player risked and what (if anything) they got back."""

    __tablename__ = "card_upgrade_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # One of the staked cards' player (the first selected, if several were
    # staked together) — same "acceptable fidelity" as the rest of this
    # audit row: it records what rarity/cost/outcome happened, not a full
    # per-card breakdown of a multi-card attempt.
    source_player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"), nullable=False)
    from_rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False)
    to_rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False)
    card_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Effective chance actually used for this attempt (base + per-extra-card
    # bonus, capped) — snapshotted, since the rule's own fields can be
    # retuned by an admin later and shouldn't rewrite past attempts' history.
    success_chance: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    coin_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_card_upgrade_attempt_idem"),)
