from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class HalloweenWallet(Base):
    """«🎃 Ночь тыкв»: a player's pumpkins for one event (`event_key`, e.g.
    "halloween-2026") — a balance of its own, never coins. Mutated only under
    the user's row lock (wallet_service.lock_user_for_update)."""

    __tablename__ = "halloween_wallets"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    pumpkins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    earned_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Pumpkins from games are capped per local day.
    games_day: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    games_pumpkins_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # «Гадость» of the doors: one of the player's footballers wears the
    # zombie frame until then (purely visual).
    zombie_player_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    zombie_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class HalloweenLedger(Base):
    """Every pumpkin in or out, plus each shop purchase and door. A non-null
    `ref_key` is unique per player — that is what makes a retried shop
    purchase, the once-a-day door and a task / chest / boss drop pay once."""

    __tablename__ = "halloween_ledger"
    __table_args__ = (UniqueConstraint("user_id", "ref_key", name="uq_halloween_ledger_user_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(32), nullable=False)
    # game / task / chest / boss / door / shop / admin
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_key: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    item_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
