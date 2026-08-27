from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TournamentQueueStatus
from app.models.mixins import utcnow


class TournamentQueueState(Base):
    """Singleton row (id=1) pointing at the currently-forming queue."""

    __tablename__ = "tournament_queue_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_queue_id: Mapped[int] = mapped_column(ForeignKey("tournament_queues.id"), nullable=False)


class TournamentQueue(Base):
    __tablename__ = "tournament_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentQueueStatus] = mapped_column(
        Enum(TournamentQueueStatus, name="tournament_queue_status_enum"),
        default=TournamentQueueStatus.open, nullable=False,
    )


class TournamentQueueEntry(Base):
    __tablename__ = "tournament_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("tournament_queues.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
