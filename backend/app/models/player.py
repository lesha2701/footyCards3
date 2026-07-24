from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Position, Rarity
from app.models.mixins import TimestampMixin


class Player(TimestampMixin, Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    club: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    position: Mapped[Position] = mapped_column(Enum(Position, name="position_enum"), nullable=False, index=True)

    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quick_sell_price: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    collection_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True
    )
    next_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    cards: Mapped[list["UserCard"]] = relationship(back_populates="player")
    collection: Mapped[Optional["CardCollection"]] = relationship(back_populates="players", lazy="joined")

    __table_args__ = ()
