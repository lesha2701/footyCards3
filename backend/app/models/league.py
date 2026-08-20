from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class LeagueTier(TimestampMixin, Base):
    """One admin-defined rung on the league ladder. A player's league is the
    highest tier whose min_rating is <= their current total rating
    (arena_rating + tactics_rating + penalty_rating, computed on read — see
    league_service.get_league_status). No is_active flag, unlike
    TrophyDefinition/WheelPrize: deleting a tier outright is the only way to
    remove one, since a "disabled" tier would create a confusing gap in the
    ladder's ordering.
    """

    __tablename__ = "league_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    min_rating: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#94a3b8")
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reward_coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ORM-level cascade (not just the DB-level ondelete="CASCADE" on the FK
    # below) so deleting a tier always cleans up its claims through
    # SQLAlchemy's own unit-of-work, regardless of whether the connected DB
    # actually enforces FK constraints (SQLite doesn't unless PRAGMA
    # foreign_keys=ON, which the test suite doesn't set) — same reasoning as
    # TrophyDefinition.grants.
    claims: Mapped[list["UserLeagueRewardClaim"]] = relationship(back_populates="tier", cascade="all, delete-orphan")


class UserLeagueRewardClaim(Base):
    """Idempotency ledger: one row per (user, tier) once that tier's reward
    has been granted. reward_coins/reward_pack_id are snapshotted at grant
    time (not read live from LeagueTier) so a later admin edit to a tier's
    reward doesn't rewrite history — same pattern as
    UserCollectionReward."""

    __tablename__ = "user_league_reward_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    league_tier_id: Mapped[int] = mapped_column(
        ForeignKey("league_tiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reward_coins: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # Purely a UI-acknowledgment flag (see league_service.mark_rewards_seen)
    # — does not gate or affect the reward itself, which is already granted
    # at tier-cross time. NULL means "granted but not yet visually shown".
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    tier: Mapped["LeagueTier"] = relationship(back_populates="claims", lazy="joined")

    __table_args__ = (UniqueConstraint("user_id", "league_tier_id"),)
