from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class UserClubBase(Base):
    """A user's «Клубная база» (services/club_base_service.py): the level of
    each building ({code: level}), the one construction in progress (shared
    with the «Академия» wings — one queue for the whole base, completed
    lazily on the next read or by the bot's sweep), the stadium's look and
    the finance department's accrued income. `total_level` (sum of the base
    buildings, without the «Академия») is kept in a column for the
    leaderboard."""

    __tablename__ = "user_club_bases"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    levels: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    total_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    building_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    building_to_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    build_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    build_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Stadium look ({"seats": color, "roof": none|canopy|full, "lights": bool,
    # "screen": bool}); options are unlocked by the stadium level.
    appearance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Sponsors + merchandise: coins accrued up to `income_since` (settled on
    # every level change at the old rate), capped at income_max_days days.
    income_accrued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    income_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class UserBaseCosmetic(Base):
    """A stadium cosmetic the user bought (GameConfig.club_base_cosmetics
    item code), forever. Unique per (user, item) — a repeated purchase or a
    re-delivered Stars payment never grants it twice."""

    __tablename__ = "user_base_cosmetics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    item_code: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)  # coins | stars
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "item_code", name="uq_user_base_cosmetics_item"),)


class ClubBaseLedger(Base):
    """Every base operation: upgrade start (coins), Stars speed-up,
    completion, income claim, stadium look. `(user_id, idempotency_key)`
    unique — a retried request is replayed, never charged twice."""

    __tablename__ = "club_base_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # upgrade | speedup | complete | income | cosmetic
    building_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    to_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    coins_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coins_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_club_base_ledger_user_key"),)
