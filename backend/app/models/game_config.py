from sqlalchemy import Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class GameConfig(TimestampMixin, Base):
    """Singleton row (id=1) holding admin-tunable game economy settings."""

    __tablename__ = "game_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    memory_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    memory_reward_cap: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    suspicious_memory_score_threshold: Mapped[int] = mapped_column(Integer, default=400, nullable=False)

    match_daily_energy: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    match_reward_win: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    match_reward_draw: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    match_reward_loss: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    difficulty_easy_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=0.85, nullable=False)
    difficulty_medium_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=1.0, nullable=False)
    difficulty_hard_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=1.2, nullable=False)
    suspicious_score_margin: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
