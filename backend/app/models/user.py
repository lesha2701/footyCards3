from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Integer, String, DateTime
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
    match_energy: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    match_energy_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    matches_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_drawn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    arena_rating: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    # Memory sequence
    memory_best_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    cards: Mapped[list["UserCard"]] = relationship(back_populates="owner", cascade="all, delete-orphan")

    def full_display_name(self) -> str:
        name = " ".join(filter(None, [self.first_name, self.last_name])).strip()
        return name or self.username or f"Player{self.telegram_id}"
