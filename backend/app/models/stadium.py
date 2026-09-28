from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import Rarity
from app.models.mixins import TimestampMixin


class Stadium(TimestampMixin, Base):
    __tablename__ = "stadiums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False, index=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quick_sell_price: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_pack_droppable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_club_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Fraction of squad strength this stadium adds when equipped, e.g. 0.05 = +5%.
    # A single flat number — unlike Coach, there is no per-zone/typed boost here.
    boost_pct: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.0)

    __table_args__ = (
        CheckConstraint("rarity != 'diamond'", name="ck_stadiums_rarity_not_diamond"),
    )
