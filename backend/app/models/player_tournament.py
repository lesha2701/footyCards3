from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TournamentQueueStatus, TournamentStatus
from app.models.mixins import utcnow


class PlayerTournament(Base):
    __tablename__ = "player_tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentStatus] = mapped_column(
        Enum(TournamentStatus, name="tournament_status_enum", create_type=False),
        default=TournamentStatus.active, nullable=False,
    )
    rounds_simulated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 30", name="ck_player_tournaments_rounds_range"),
    )


class PlayerTournamentParticipant(Base):
    __tablename__ = "player_tournament_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_participant_once"),)


class PlayerTournamentStanding(Base):
    __tablename__ = "player_tournament_standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_standing_once"),)


class PlayerTournamentMatch(Base):
    __tablename__ = "player_tournament_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    score_a: Mapped[int] = mapped_column(Integer, nullable=False)
    score_b: Mapped[int] = mapped_column(Integer, nullable=False)
    event_log: Mapped[list] = mapped_column(JSON, nullable=False)
    simulated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Card-skill effects frozen for this match ({"a": {card_id: effect}, "b": ...});
    # NULL for matches without any skill effect, including every pre-skill match.
    skill_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("round_number >= 1 AND round_number <= 30", name="ck_player_tournament_matches_round_range"),
    )


class PlayerTournamentResult(Base):
    __tablename__ = "player_tournament_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    coins_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    stars_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    cup_awarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_result_once"),)


class PlayerTournamentQueueState(Base):
    """Singleton row (id=1) pointing at the currently-forming queue."""

    __tablename__ = "player_tournament_queue_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_queue_id: Mapped[int] = mapped_column(ForeignKey("player_tournament_queues.id"), nullable=False)


class PlayerTournamentQueue(Base):
    __tablename__ = "player_tournament_queues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentQueueStatus] = mapped_column(
        Enum(TournamentQueueStatus, name="tournament_queue_status_enum", create_type=False),
        default=TournamentQueueStatus.open, nullable=False,
    )


class PlayerTournamentQueueEntry(Base):
    __tablename__ = "player_tournament_queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("player_tournament_queues.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("queue_id", "user_id", name="uq_player_tournament_queue_entry_once"),)
