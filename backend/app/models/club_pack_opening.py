from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import utcnow


class ClubPackOpening(Base):
    __tablename__ = "club_pack_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    club_pack_id: Mapped[int] = mapped_column(ForeignKey("club_packs.id"), nullable=False)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    price_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    cards: Mapped[list["ClubPackOpeningCard"]] = relationship(back_populates="opening", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("club_id", "idempotency_key", name="uq_club_pack_opening_idempotency"),)


class ClubPackOpeningCard(Base):
    __tablename__ = "club_pack_opening_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opening_id: Mapped[int] = mapped_column(ForeignKey("club_pack_openings.id", ondelete="CASCADE"), nullable=False, index=True)
    club_card_id: Mapped[int] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False)
    is_new_player: Mapped[bool] = mapped_column(Boolean, nullable=False)

    opening: Mapped["ClubPackOpening"] = relationship(back_populates="cards")
