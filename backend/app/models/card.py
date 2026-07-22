from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CardSource
from app.models.mixins import utcnow


class UserCard(Base):
    __tablename__ = "user_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Assigned in application code from the row's own id right after insert (see
    # services/card_creation.py) — portable across databases, unlike a DB-level
    # IDENTITY/sequence on a non-PK column. Nullable only for the instant between
    # the initial INSERT (which needs the id) and that follow-up UPDATE, both of
    # which happen inside the same transaction before it is ever committed.
    serial_number: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"), nullable=False, index=True)

    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source: Mapped[CardSource] = mapped_column(Enum(CardSource, name="card_source_enum"), nullable=False)
    source_ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_locked_by_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked_in_trade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_in_lineup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="cards")
    player: Mapped["Player"] = relationship(back_populates="cards")

    def is_locked(self) -> bool:
        return self.is_locked_by_admin or self.is_locked_in_trade or self.is_in_lineup

    __table_args__ = (UniqueConstraint("serial_number", name="uq_user_cards_serial"),)
