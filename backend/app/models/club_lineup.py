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
    formation: Mapped[str] = mapped_column(String(16), default="4-3-3", nullable=False, server_default="4-3-3")
    mentality: Mapped[str] = mapped_column(String(16), default="BALANCED", nullable=False, server_default="BALANCED")
    playstyle: Mapped[str] = mapped_column(String(16), default="CENTRAL_PLAY", nullable=False, server_default="CENTRAL_PLAY")
    club_coach_card_id: Mapped[int | None] = mapped_column(ForeignKey("club_coach_cards.id", ondelete="SET NULL"), nullable=True)

    cards: Mapped[list["ClubLineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")
    club_coach_card: Mapped["ClubCoachCard | None"] = relationship(lazy="joined")


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
