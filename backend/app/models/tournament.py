from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TournamentStatus
from app.models.mixins import utcnow


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[TournamentStatus] = mapped_column(
        Enum(TournamentStatus, name="tournament_status_enum"), default=TournamentStatus.active, nullable=False,
    )
    rounds_simulated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # ChemistryRules.as_dict() frozen when the club tournament starts; NULL =
    # the neighbour-link chemistry was off then (incl. every tournament that
    # predates it), and stays off for this tournament's whole run — same
    # contract as PlayerTournament.chemistry_rules.
    chemistry_rules: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 14", name="ck_tournaments_rounds_simulated_range"),
    )


class TournamentClub(Base):
    __tablename__ = "tournament_clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    is_withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "club_id", name="uq_tournament_clubs_once"),)
