from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import Position
from app.models.mixins import utcnow


class MyPlayer(Base):
    """"Мой игрок": the user's own footballer, built in a constructor
    (appearance), leveled with XP (User.my_player_xp) into attribute points.
    Deliberately NOT a Player/UserCard row: it can't be sold, traded, fed to
    upgrades or dropped from packs, and never shows up in albums or bot
    squads. Game modes field it through a duck-typed engine card (see
    my_player_service.engine_card): "Карьера тренера" and «Футбольное
    Стратего» (any role in the pre-match squad, see stratego_service)."""

    __tablename__ = "my_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(24), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    position: Mapped[Position] = mapped_column(Enum(Position, name="position_enum", create_type=False), nullable=False)
    # {"skin", "hair", "hair_color", "beard", "eye_color", "kit", "kit_pattern"} — option
    # indexes, see my_player_service.APPEARANCE_OPTIONS.
    appearance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {"atk", "def"}: 1-99 — the same attack/defense every card has.
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    points_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Card skill (card_skill_catalog code). NULL = none chosen.
    skill_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Bought level of that skill (tokens + coins); the player level caps
    # the level actually used (config.my_player_skill_levels).
    skill_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # {"owned": [codes], "accessory": code | None, "background": code | None}
    cosmetics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Daily training: local date it was done, and when the current run started.
    training_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    training_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Extra trainings bought for coins/Stars: unused credits (kept until
    # spent) and how many were bought on extra_training_day (daily max).
    extra_training_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_trainings_bought: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_training_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # «Карьера игрока»: current club (player_career_service club key),
    # reputation (opens bigger clubs) and lifetime stats
    # {"seasons", "matches", "goals", "assists", "titles", "top_scorer", "mvp"}.
    club_key: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    reputation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    career_stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
