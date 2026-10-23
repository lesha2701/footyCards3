from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class KontraBattle(Base):
    """One «Контратака» battle: an arena attack on another player's defence
    squad (or a bot's) or an attempt on the weekly boss. The whole fight
    (units, turn meter, effects, event log) lives in server_state;
    `version` grows with every action (stale → 409, a retried action is a
    no-op — see kontra_service.act)."""

    __tablename__ = "kontra_battles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # arena | boss
    opponent_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opponent_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_progress", index=True)
    result: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # win | loss
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    damage: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # The boss's week (Monday) — weekly damage tables sum over it.
    boss_week: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    gear_drop_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class KontraGear(Base):
    """A «Тактический комплект» piece. `card_id` is the card wearing it (a
    UserCard id, or «Мой игрок»'s negative stand-in id) — checked against
    the owner whenever it's used, never a foreign key."""

    __tablename__ = "kontra_gear"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    set_code: Mapped[str] = mapped_column(String(16), nullable=False)
    rarity: Mapped[str] = mapped_column(String(16), nullable=False)
    card_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # boss / arena / chest / stars / admin
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # Stars deliveries: the invoice token, so a redelivery grants nothing new.
    source_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
