from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TournamentClubResult(Base):
    __tablename__ = "tournament_club_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    stars_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    cup_awarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_results_once"),)
