from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
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


class PlayerCareerCup(Base):
    """A knockout cup of «Карьера игрока»: the Champions League (kind "cl",
    after a top-league season) or the national-team tournament (kind
    "national", every two weeks for called-up players). 8 teams, three
    rounds at the career slots; bracket and the player's stats in `state`."""

    __tablename__ = "player_career_cups"
    __table_args__ = (UniqueConstraint("user_id", "kind", "window_key", name="uq_player_career_cup_window"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    window_key: Mapped[str] = mapped_column(String(32), nullable=False)
    # active | finished
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    coins_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PlayerCareerMonthStat(Base):
    """Per-month totals of every «Карьера игрока» match (league and cups) —
    the «Золотой мяч» race."""

    __tablename__ = "player_career_month_stats"
    __table_args__ = (UniqueConstraint("user_id", "month", name="uq_player_career_month_stat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # "YYYY-MM", local time.
    month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clean_sheets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_sum: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    # GK | DEF | MID | FWD — the line of the last match (sets the score weights).
    line: Mapped[str] = mapped_column(String(8), nullable=False, default="FWD")


class PlayerCareerGoldenBall(Base):
    """One «Золотой мяч» per month; the primary key keeps it awarded once."""

    __tablename__ = "player_career_golden_balls"

    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    goals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_rating: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
