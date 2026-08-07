from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    game_rewards_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    received_starting_bonus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Card Arena stats
    matches_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_drawn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    arena_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Lifetime counters feeding `metric_counter` tasks (see task_service.py).
    arena_clean_sheet_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_levels_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saboteur_levels_cleared: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Tactico stats
    tactics_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tactico_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tactico_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Memory sequence
    memory_best_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    memory_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Card Arena hourly limit
    match_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    match_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Saboteur
    saboteur_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saboteur_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    saboteur_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saboteur_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Penalty
    penalty_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalty_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    penalty_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalty_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Free Kick
    free_kick_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_kick_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    free_kick_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_kick_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Football Hangman
    hangman_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hangman_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hangman_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hangman_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Найди пару (card pairs memory match)
    pairs_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pairs_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pairs_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pairs_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Free pack (every N hours)
    free_pack_available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    free_pack_notified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Chat mode promo pack ("вкарта" command in group chats, every N hours) —
    # a separate cooldown from free_pack_available_at so the two mechanics
    # don't compete with each other.
    chat_pack_available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Consecutive days played, tracked off daily-reward claims — unlike
    # DailyReward.streak_day (which cycles 1-7 to pick a reward tier), this
    # keeps counting up so the profile can show an uncapped "days in a row".
    daily_login_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Referrals
    referred_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    referral_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referral_reward_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Trade privacy
    accept_trades: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Currently-equipped Badge (if any), shown next to this user's name
    # everywhere a public identity is rendered. `lazy="joined"` so every
    # query touching User eager-loads it — this is read almost everywhere
    # User is serialized, and async SQLAlchemy can't lazy-load on demand.
    active_badge_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("badges.id", ondelete="SET NULL"), nullable=True
    )
    active_badge: Mapped[Optional["Badge"]] = relationship(lazy="joined")

    cards: Mapped[list["UserCard"]] = relationship(back_populates="owner", cascade="all, delete-orphan")

    def full_display_name(self) -> str:
        name = " ".join(filter(None, [self.first_name, self.last_name])).strip()
        return name or self.username or f"Player{self.telegram_id}"
