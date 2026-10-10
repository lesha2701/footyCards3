from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
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
    final_place: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    coins_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    season: Mapped["CareerSeason"] = relationship(back_populates="participants")

    __table_args__ = (
        UniqueConstraint("season_id", "user_id", name="uq_career_participant"),
        Index("ix_career_participants_season", "season_id"),
    )


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
