from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class Lineup(TimestampMixin, Base):
    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Основной состав")
    formation: Mapped[str] = mapped_column(String(16), nullable=False, default="4-3-3")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cards: Mapped[list["LineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")


class LineupCard(Base):
    __tablename__ = "lineup_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lineup_id: Mapped[int] = mapped_column(ForeignKey("lineups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[int] = mapped_column(
        ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Formation slot code, e.g. "GK", "DEF1".."DEF4", "MID1".."MID3", "FWD1".."FWD3"
    slot_code: Mapped[str] = mapped_column(String(16), nullable=False)

    lineup: Mapped["Lineup"] = relationship(back_populates="cards")

    __table_args__ = (
        UniqueConstraint("lineup_id", "user_card_id", name="uq_lineup_card_once"),
        UniqueConstraint("lineup_id", "slot_code", name="uq_lineup_slot_once"),
    )
