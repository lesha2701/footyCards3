from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class CareerSeason(Base):
    """"Карьера тренера": an 8-team double round-robin (14 rounds, two a day
    for a week) — the player's own cards against bots, optionally with one
    friend in the same league. Fixtures, schedule, bot squads and results
    live in the JSON `state` (same pattern as GameSession/TacticoMatch
    server_state); see services/career_service.py."""

    __tablename__ = "career_seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # pending (waiting for an invited friend) | active | finished | cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="pro")
    # Division (1 = top) the league is played in; sets bot strength, bot
    # level (difficulty above) and rewards. None = season from before
    # divisions (difficulty was picked by hand).
    division: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invite_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list["CareerParticipant"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", lazy="selectin",
    )


class CareerParticipant(Base):
    """A human in a career season. squad_card_ids = the 16-card squad (own
    cards only), lineup = {slot_code: user_card_id} for the coming rounds
    (None = auto-pick), condition = {card_id: {"fatigue": 0-100,
    "injured_until": round index the card is back}}."""

    __tablename__ = "career_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("career_seasons.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    team_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # invited | accepted | declined
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="accepted")
    squad_card_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    lineup: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    formation: Mapped[str] = mapped_column(String(16), nullable=False, default="4-3-3")
    mentality: Mapped[str] = mapped_column(String(16), nullable=False, default="BALANCED")
    playstyle: Mapped[str] = mapped_column(String(16), nullable=False, default="CENTRAL_PLAY")
    condition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Сыгранность (tactics_version >= 1 seasons, career_tactics_service):
    # tenths of a % rating bonus for familiar_formation + familiar_tactic,
    # the tactic played in the last match. match_plan = conditional
    # instructions + substitutions for the coming rounds (snapshotted into
    # the match result at kick-off).
    familiarity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    familiar_formation: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    familiar_tactic: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Tactical axes (career_tactics_service.AXES) for tactics seasons;
    # `playstyle` then holds the matching preset code or CUSTOM.
    tactic: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    match_plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Set-piece takers and schemes (career_tactics_service.DEFAULT_SET_PIECES).
    set_pieces: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Player roles per line ({group: value}, career_tactics_service.ROLE_GROUPS)
    # and man-marking for one round ({"round", "marker", "target"}).
    roles: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    marking: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Board objective chosen for this season (survive / mid / promote) and
    # the training focus before the next round (career_service.TRAININGS).
    ambition: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    training: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # Off-season: preseason camp focus, how many squad cards carried over
    # from the previous season (the "core"), and the familiarity carried
    # over (before the camp's own bonus).
    camp: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    core_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    carried_familiarity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # The participant's own division when the season started and where the
    # final place sends them (promotion / relegation), set at the finish or
    # on leaving. A friend may play in the creator's division, but moves up
    # or down from their own.
    division: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_division: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    final_place: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    coins_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    season: Mapped["CareerSeason"] = relationship(back_populates="participants")

    __table_args__ = (
        UniqueConstraint("season_id", "user_id", name="uq_career_participant"),
        Index("ix_career_participants_season", "season_id"),
    )


class CareerProfile(Base):
    """Long-term coach career of a user across seasons: the division the next
    season is played in, reputation (never reset), a few counters, the last
    time the user opened the career (inactive coaches drop a division at
    the season change) and per-card club tenure (minutes played)."""

    __tablename__ = "career_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    division: Mapped[int] = mapped_column(Integer, nullable=False)
    reputation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    seasons_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    titles: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    promotions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    objectives_met: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # card id -> minutes played in career matches (club tenure, off-season).
    tenure: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Persistent league / rivals history (off-season).
    league: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # career_achievements_service: unlocked achievements, the trophy cabinet,
    # running streaks and the weekly digest bookkeeping.
    achievements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CareerClub(Base):
    """A bot club of a career division (admin-editable). source: "real" =
    named after a real club in the card pool, its roster drawn from that
    club's players (gaps filled with others); "generated" = an invented
    club with players from the whole pool; "admin" = added by hand."""

    __tablename__ = "career_clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    division: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="generated")
    # Club name in the player pool whose players form the roster (real clubs).
    pool_club: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # ± rating vs the division's bot strength.
    rating_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    formation: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    preset: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Friendship(Base):
    """Friends: one row per pair. pending = `requester_id` asked, accepted =
    mutual. user_low/user_high (min/max id) keep the pair unique whoever
    asked first."""

    __tablename__ = "friendships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_low: Mapped[int] = mapped_column(Integer, nullable=False)
    user_high: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_low", "user_high", name="uq_friendship_pair"),)
