from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import Position
from app.models.mixins import utcnow


class AcademyProspect(Base):
    """«Воспитанник Академии» (services/prospect_service.py): a child the user
    raises from 6 years old. Age follows the calendar (config days_per_year
    real days = one year), the rating follows XP and is capped by the age
    stage and by the hidden potential. Like «Мой игрок» it is NOT a
    Player/UserCard row: never sold, traded, fed or dropped from packs; game
    modes field it through a duck-typed stand-in.

    One "growing" child per user at a time. At the «Дебют» stage he may
    graduate: the row turns "graduate" with a frozen `final_rating` (plays in
    «Менеджер», one per user) and the user starts the next generation; the
    previous graduate then retires ("retired") to the hall."""

    __tablename__ = "academy_prospects"
    __table_args__ = (
        Index("uq_academy_prospects_growing", "user_id", unique=True,
              postgresql_where=text("status = 'growing'"), sqlite_where=text("status = 'growing'")),
        Index("uq_academy_prospects_graduate", "user_id", unique=True,
              postgresql_where=text("status = 'graduate'"), sqlite_where=text("status = 'graduate'")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # growing | graduate | retired
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="growing")
    # «Династия»: the n-th child of this user.
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    graduated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    final_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Talents picked at stages (prospect_life.SPECS codes), in order.
    specs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # «Турнир набора»: XP of the current ISO week and of the last finished one.
    week_key: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    week_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_week_key: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    last_week_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # «Менеджер»: {season_key: value €} at season starts (the ▲/▼ trend).
    value_history: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    name: Mapped[str] = mapped_column(String(24), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    position: Mapped[Position] = mapped_column(Enum(Position, name="position_enum", create_type=False), nullable=False)
    foot: Mapped[str] = mapped_column(String(8), nullable=False, default="right")
    # my_player_service.APPEARANCE_OPTIONS indexes — the same constructor.
    appearance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Hidden potential ★1-5: sets the peak rating. Revealed by a scout (Stars)
    # or on its own at the U-19 stage.
    potential: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    potential_revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # A universal player until «Юноши»: there the position is picked from the
    # coach's offers (False until then; `position` is a provisional CM).
    position_set: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # +peak rating from the owner's «Академия» level (every N levels), never lowered.
    academy_peak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Capped XP (matches) earned on xp_day.
    xp_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    xp_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Daily training: the day the free one was done, the streak ending on it,
    # bought credits (kept until spent) and how many were bought on extra_day.
    training_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    training_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_bought: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Story fork: the day the last one was answered.
    story_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # «Личный тренер» (Stars) active until.
    coach_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # A «Академия» path card of the owner as mentor (+XP while still owned).
    mentor_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True)
    # {"owned": [codes], "background": code | None, "accessory": code | None}
    cosmetics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # [{"day": "YYYY-MM-DD", "code", "text"}] — the album of growing up.
    memories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # {"matches", "goals", "wins", "trainings", "stories": [codes seen]}
    stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Seeds the NPC rival of the same age.
    rival_seed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # «Менеджер»: listed on the free-agent market (any manager may offer a contract).
    market_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ProspectDuel(Base):
    """An async «Ответка» duel of two friends' prospects: each plays his own
    match (any order, until `expires_at`); the better result wins
    (prospect_life.settle_duel). status: open | done | expired."""

    __tablename__ = "prospect_duels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    challenger_session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opponent_session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # {"for": goals, "against": goals, "won": bool}
    challenger_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    opponent_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    winner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProspectLedger(Base):
    """Every coin / Stars purchase for the prospect; the unique key makes a
    retried request or a redelivered payment a no-op."""

    __tablename__ = "prospect_ledger"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_prospect_ledger_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(96), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
