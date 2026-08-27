from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class TournamentSimulationSlotLog(Base):
    """Backend-side dedup record for the bot's two daily scheduler loops.
    A row here means "this (kind, slot_key) has already been processed" —
    checked via a try-insert-and-catch-IntegrityError, not an in-memory
    flag, so a bot restart (which resets any in-memory state) can never
    cause a slot to be processed twice. `slot_key` is derived from the
    SLOT's nominal time (e.g. "2026-08-27T12:00"), not wall-clock `now` —
    a late catch-up fire for a missed slot must produce the same key as
    an on-time fire would have, so they dedup against each other."""

    __tablename__ = "tournament_simulation_slot_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # "simulate_round" | "lineup_reminders"
    slot_key: Mapped[str] = mapped_column(String(32), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("kind", "slot_key", name="uq_tournament_simulation_slot_log_once"),)
