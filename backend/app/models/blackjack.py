from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class BlackjackMatch(Base):
    """One hand of «21: Добавленное время» against the bot. The shuffled
    deck and the bot's hole card live only in server_state ({"deck": [...],
    "player": [...], "dealer": [...]}) and are filtered out by
    blackjack_service._match_out until the hand is over (the remaining deck
    is never sent at all).

    At most one in_progress match per user — enforced by the partial unique
    index below, not just by a pre-check. The reward is paid exactly once:
    the status flip to "finished" happens under a row lock, and a won
    match's WheelSpin carries a UNIQUE blackjack_match_id."""

    __tablename__ = "blackjack_matches"
    __table_args__ = (
        Index(
            "uq_blackjack_matches_one_active", "user_id", unique=True,
            postgresql_where=text("status = 'in_progress'"), sqlite_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # in_progress / finished
    status: Mapped[str] = mapped_column(String(16), default="in_progress", nullable=False)
    # Which entry paid for this hand: free (daily), paid (Stars), replay (a draw).
    entry_source: Mapped[str] = mapped_column(String(16), nullable=False)
    server_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    # hat_trick / win / push / loss (blackjack_engine.OUTCOME_*)
    outcome: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # natural / both_natural / dealer_natural / offside / dealer_offside / higher / lower / equal
    outcome_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # golden / jackpot for a win, else NULL.
    reward_pool: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    consolation_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
