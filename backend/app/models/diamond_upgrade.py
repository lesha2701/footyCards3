from typing import Optional

from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class DiamondUpgradeTier(TimestampMixin, Base):
    """Admin-tunable cost table for leveling up a diamond card's rating by
    feeding it other cards. Rows cover non-overlapping rating bands
    [min_rating, max_rating); the diamond card's CURRENT effective rating
    picks which row applies. Each *_cost is "how many cards of that rarity,
    fed in one submission, buys +1 rating" at this band — admin adds rows
    for higher bands as needed, there is no fixed set of bands. A NULL cost
    means that rarity cannot be used to level up a card in this band."""

    __tablename__ = "diamond_upgrade_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    min_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    max_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    common_cost: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rare_cost: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    epic_cost: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    legendary_cost: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
