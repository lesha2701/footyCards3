"""Weekly and daily events on top of existing modes:

- «Неделя мини-игры» (weekly_cup_service): one solo mini-game a week,
  a leaderboard of the sum of each player's best N games, prizes for the
  top places;
- «Матч дня» (match_day_service): a real match an admin enters, players
  guess the score before kickoff and claim coins after the result;
- «Клубный рейд» (club_raid_service): a weekly boss for every club, the
  members' attacks add up to defeat it."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class WeeklyCupWeek(Base):
    """The week's game, frozen on the first read of the week (an admin
    changing the rotation mid-week doesn't switch it); `settled_at` once the
    results are written — the once-guard of the settlement."""
    __tablename__ = "weekly_cup_weeks"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    game: Mapped[str] = mapped_column(String(24), nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class WeeklyCupResult(Base):
    """A participant's final place; a prize is claimed by the player."""
    __tablename__ = "weekly_cup_results"
    __table_args__ = (UniqueConstraint("week_start", "user_id", name="uq_weekly_cup_result"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    place: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    games: Mapped[int] = mapped_column(Integer, nullable=False)
    prize_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MatchDayFixture(Base):
    __tablename__ = "match_day_fixtures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    home: Mapped[str] = mapped_column(String(64), nullable=False)
    away: Mapped[str] = mapped_column(String(64), nullable=False)
    league: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MatchDayPrediction(Base):
    """One guess per player and match, editable until kickoff. The reward is
    fixed when the player claims it (after the result)."""
    __tablename__ = "match_day_predictions"
    __table_args__ = (UniqueConstraint("fixture_id", "user_id", name="uq_match_day_prediction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("match_day_fixtures.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    home: Mapped[int] = mapped_column(Integer, nullable=False)
    away: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_coins: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ClubRaid(Base):
    """A club's boss of the week. `hp` is fixed when the raid opens (by the
    member count then); `damage` only grows, under this row's lock."""
    __tablename__ = "club_raids"
    __table_args__ = (UniqueConstraint("club_id", "week_start", name="uq_club_raid_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    boss: Mapped[str] = mapped_column(String(24), nullable=False)
    hp: Mapped[int] = mapped_column(Integer, nullable=False)
    damage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    defeated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClubRaidAttack(Base):
    __tablename__ = "club_raid_attacks"
    __table_args__ = (Index("ix_club_raid_attacks_user_day", "user_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raid_id: Mapped[int] = mapped_column(ForeignKey("club_raids.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # The local day — the daily attack limit counts across clubs.
    day: Mapped[date] = mapped_column(Date, nullable=False)
    shots: Mapped[int] = mapped_column(Integer, nullable=False)
    goals: Mapped[int] = mapped_column(Integer, nullable=False)
    damage: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
