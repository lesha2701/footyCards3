from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class ClubLineup(Base):
    __tablename__ = "club_lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cards: Mapped[list["ClubLineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")


class ClubLineupCard(Base):
    __tablename__ = "club_lineup_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_lineup_id: Mapped[int] = mapped_column(ForeignKey("club_lineups.id", ondelete="CASCADE"), nullable=False, index=True)
    club_card_id: Mapped[int] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_code: Mapped[str] = mapped_column(String(16), nullable=False)

    lineup: Mapped["ClubLineup"] = relationship(back_populates="cards")
    club_card: Mapped["ClubCard"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("club_lineup_id", "club_card_id", name="uq_club_lineup_card_once"),
        UniqueConstraint("club_lineup_id", "slot_code", name="uq_club_lineup_slot_once"),
    )
