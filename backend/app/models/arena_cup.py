from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ArenaCupRun(Base):
    """One player's run in one weekend's cup: knockout rounds against
    stronger and stronger sides; the unique row is what stops a second run."""
    __tablename__ = "arena_cup_runs"
    __table_args__ = (UniqueConstraint("user_id", "week_key", name="uq_arena_cup_runs_user_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    week_key: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    rounds_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # active | lost | champion
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
