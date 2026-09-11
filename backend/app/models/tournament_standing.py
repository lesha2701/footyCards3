from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TournamentClubStanding(Base):
    __tablename__ = "tournament_club_standings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # "Тренировка состава" — a one-tour-only ~10% squad boost, up to
    # club_training_uses_per_tournament activations per tournament (set explicitly from
    # GameConfig at row-creation time in tournament_queue_service.apply_to_tournament, not from
    # this column's own Python default — see that function). Resets automatically every
    # tournament: this whole row is freshly created per (tournament, club), enforced by
    # uq_tournament_club_standings_once, so there is no separate "reset" code path.
    training_uses_remaining: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # The tournament round number this club's next-activated boost applies to, or NULL if no
    # boost is currently pending. Set to rounds_simulated+1 on activation; cleared back to NULL
    # the moment that round is actually simulated (tournament_simulation_service), whether or
    # not consumed — the boost never rolls over.
    training_boost_round: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_standings_once"),)
