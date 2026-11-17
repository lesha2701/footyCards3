from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class MagicRun(Base):
    """One «Мяч и Магия» run: the adventure map, the army and the battle in
    progress all live in server_state (magic_engine); `version` grows with
    every action (stale → 409, a retried action returns the run unchanged)."""

    __tablename__ = "magic_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    faction: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_progress", index=True)
    result: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # win | loss
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # A won pack: the opening (its cards show on the result screen).
    pack_opening_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # The weekly challenge this run is for ("2026-W46"): the same map for everyone.
    challenge_week: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
