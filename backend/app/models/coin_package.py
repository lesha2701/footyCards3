from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class CoinPackage(TimestampMixin, Base):
    """An admin-defined coin denomination purchasable with Telegram Stars —
    replaces the earlier formula-based rate/bulk-bonus (GameConfig.stars_to_coins_rate
    and friends), so the admin can set exact, non-linear amounts per tier
    instead of one global rate."""

    __tablename__ = "coin_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stars_price: Mapped[int] = mapped_column(Integer, nullable=False)
    coins_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
