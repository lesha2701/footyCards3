from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class FanBattleMember(Base):
    """«⚔️ Битва фанатов»: the side a player picked for one event
    (`event_key`, e.g. "fans-2026") — once, for the whole event — and the
    points he brought it. Mutated only under the user's row lock."""

    __tablename__ = "fan_battle_members"
    __table_args__ = (Index("ix_fan_battle_members_event_side_points", "event_key", "side", "points"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Points from games are capped per local day.
    games_day: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    games_points_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FanBattleLedger(Base):
    """Every point a player brought his side (with the side and the local
    `day`, so the side totals of a day are a SUM — no hot counter row) and
    every reward claim (delta 0). A non-null `ref_key` is unique per player:
    a task / chest / boss drop and each daily / milestone / final reward pay
    once."""

    __tablename__ = "fan_battle_ledger"
    __table_args__ = (
        UniqueConstraint("user_id", "ref_key", name="uq_fan_battle_ledger_user_ref"),
        Index("ix_fan_battle_ledger_event_day_side", "event_key", "day", "side"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    # game / task / chest / boss / admin — points; daily / milestone / final — claims
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_key: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
