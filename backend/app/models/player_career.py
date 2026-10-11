from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class PlayerCareerSeason(Base):
    """«Карьера игрока»: one week-long league season of «Мой игрок» at a club
    built from the real cards of that club (see player_career_service). The
    league (8 clubs of similar strength, frozen squads), fixtures, schedule,
    results and the player's per-round stats live in the JSON `state`, the
    same pattern as CareerSeason. One active season per user."""

    __tablename__ = "player_career_seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    club_key: Mapped[str] = mapped_column(String(96), nullable=False)
    # active | finished | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    final_place: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    coins_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
