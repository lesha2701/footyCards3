"""«Академия» — diamond cards of young players that grow by playing.

What lives where (see docs/path-cards.md):
  * Player.path_talent_code — a Player design IS a path card when this is set
    (it must also be Rarity.diamond); the talent is chosen by the admin.
  * UserCard.path_level / path_stage / path_rating_bonus — what this copy has
    reached; the rating bonus is fixed on the row when a level is gained (like
    diamond_rating_bonus) and folded into player_stats_service.card_rating_bonus.
  * CardPath — the rest of one copy's progress (experience, the current
    stage's task counters, daily limits, bought attempts, «Голод» streak).
    Keyed by user_cards.id, so it travels with the card on a trade.
  * PathStage / PathStageTask / PathTalent — admin-editable catalog: stage
    bounds and talent levels, the stage gates, each talent's strength.
  * PathXpEvent — one row per (card, match): the unique constraint makes a
    retried / concurrently re-run award a no-op.
  * PathAttemptPurchase — every bought extra Arena attempt (coins or Stars).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class PathTalent(TimestampMixin, Base):
    """Admin-editable state of one talent from the server catalog
    (services/path_talent_catalog.TALENTS). The catalog owns what a talent
    DOES; this row owns whether it may be assigned to new players, its
    strength per level and display order. A disabled talent keeps working
    on players that already have it only if `is_enabled` — switching it off
    removes its effect from new matches (already-started ones keep their
    frozen snapshot)."""

    __tablename__ = "path_talents"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # {"1": {"bonus": 3, ...}, "2": {"bonus": 5, ...}} — keys validated
    # against the catalog's params on write; missing keys fall back to the
    # catalog defaults.
    level_values: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PathStage(TimestampMixin, Base):
    """One stage of the path (Новичок … Легенда). A card is in the stage
    whose rating band contains its current rating; `max_rating` is the
    stage's upper bound (the last stage's bound is the path's ceiling).
    Leaving a stage needs its tasks done (PathStageTask)."""

    __tablename__ = "path_stages"

    stage_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    max_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    # Talent level unlocked on reaching this stage (0 = none yet).
    talent_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PathStageTask(TimestampMixin, Base):
    """A gate task of a stage: `target` of `metric` counted since the card
    entered the stage, only from matches that earned path experience.
    `positions` (null = everyone) limits who must do it — e.g. goal tasks
    only for attacking players; a card outside the list skips the task."""

    __tablename__ = "path_stage_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage_index: Mapped[int] = mapped_column(
        ForeignKey("path_stages.stage_index", ondelete="CASCADE"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    positions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CardPath(Base):
    __tablename__ = "card_paths"

    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), primary_key=True)
    # Experience earned in total (never spent): the level follows from it,
    # capped by the stage whose tasks are not done yet.
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # metric -> count since the card entered its current stage.
    stage_counters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # metric -> count over the card's whole life (shown on the path screen).
    totals: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Daily limits (local day, core.timeutil.local_today): reset lazily.
    day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    arena_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    career_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ptour_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coin_buys: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_buys: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Bought extra Arena attempts not used yet — they never expire.
    bought_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # «Голод»: Card Arena matches in a row with this card in the lineup.
    hunger_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class PathXpEvent(Base):
    __tablename__ = "path_xp_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # arena | ptour | career
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # {"result", "goals", "assists", "attempt": "free|bought|career|ptour", "levels": [..]}
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_card_id", "source_type", "source_id", name="uq_path_xp_events_card_source"),
    )


class PathPrestigeLedger(Base):
    """Every prestige tier-up (duplicates burnt, coins, reward) and talent
    reforge. `(user_id, idempotency_key)` unique = a retried request replays."""

    __tablename__ = "path_prestige_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # tier_up | reforge
    tier_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_card_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    coins_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    from_talent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_talent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_path_prestige_ledger_user_key"),)


class PathAttemptPurchase(Base):
    __tablename__ = "path_attempt_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)  # coins | stars
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_day: Mapped[date] = mapped_column(Date, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_path_attempt_purchases_user_key"),)
