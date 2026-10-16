"""Monetization & retention: cosmetics, the monthly login calendar, «Клубный
абонемент» (Stars subscription), «Сезонный пропуск» and the one-time
starter offer. Every reward slot below uses the same five optional fields
(see services/reward_bundle_service.py): coins, a pack, a random card of a
rarity, a badge and a cosmetic."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow

COSMETIC_KINDS = ("profile_frame", "profile_background", "card_skin")


class Cosmetic(TimestampMixin, Base):
    """A purely visual item — never read by match/rating code. `style_key`
    picks one of the looks the frontend knows how to draw
    (frontend/src/lib/cosmetics.ts); `is_exclusive` items are never sold,
    only granted (club pass, season pass, starter offer, calendar)."""

    __tablename__ = "cosmetics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    style_key: Mapped[str] = mapped_column(String(32), nullable=False)
    # 0 = not sold for that currency.
    coins_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_exclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserCosmetic(Base):
    """Ownership. `source` says where it came from; "club_pass" items are
    taken back when the subscription runs out."""

    __tablename__ = "user_cosmetics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    cosmetic_id: Mapped[int] = mapped_column(ForeignKey("cosmetics.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cosmetic: Mapped["Cosmetic"] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("user_id", "cosmetic_id", name="uq_user_cosmetic"),)


class RewardSlotMixin:
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    card_rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="SET NULL"), nullable=True)
    cosmetic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True)


class LoginCalendarDay(RewardSlotMixin, Base):
    """The monthly login calendar template — the same for every month. Day
    1..31 (days past the month's length are simply not shown); day 0 is the
    bonus for claiming every day of a month."""

    __tablename__ = "login_calendar_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)


class LoginCalendarBonusClaim(Base):
    __tablename__ = "login_calendar_bonus_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)  # first day of the month
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "month", name="uq_login_calendar_bonus_user_month"),)


class ClubSubscription(TimestampMixin, Base):
    """«Клубный абонемент»: one row per player, kept across renewals and
    lapses. Active while `expires_at` is in the future. `telegram_charge_id`
    is the first payment of the current Telegram subscription — what
    editUserStarSubscription needs to cancel/resume auto-renewal."""

    __tablename__ = "club_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    telegram_charge_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_daily_claim: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Exclusive items were granted for the current period (revoked lazily
    # once it lapses).
    perks_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Season(TimestampMixin, Base):
    """«Сезонный пропуск» season. The active one is the season whose
    [starts_at, ends_at) contains now."""

    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    premium_stars: Mapped[int] = mapped_column(Integer, default=399, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SeasonLevel(Base):
    """One level of a season: reached at `xp_required` total XP; a free and
    a premium reward slot (premium_* fields)."""

    __tablename__ = "season_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    xp_required: Mapped[int] = mapped_column(Integer, nullable=False)
    free_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    free_card_rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    free_badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="SET NULL"), nullable=True)
    free_cosmetic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )
    premium_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    premium_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    premium_card_rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    premium_badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="SET NULL"), nullable=True)
    premium_cosmetic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (UniqueConstraint("season_id", "level", name="uq_season_level"),)


class SeasonProgress(Base):
    __tablename__ = "season_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False, index=True)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    premium_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "season_id", name="uq_season_progress_user"),)


class SeasonClaim(Base):
    __tablename__ = "season_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("season_levels.id", ondelete="CASCADE"), nullable=False)
    track: Mapped[str] = mapped_column(String(8), nullable=False)  # "free" | "premium"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "level_id", "track", name="uq_season_claim"),)


class StarterOfferPurchase(Base):
    """The one-time starter offer was bought (unique per user)."""

    __tablename__ = "starter_offer_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    stars_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
