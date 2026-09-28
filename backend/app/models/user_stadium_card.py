from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CardSource
from app.models.mixins import utcnow


class UserStadiumCard(Base):
    __tablename__ = "user_stadium_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stadium_id: Mapped[int] = mapped_column(ForeignKey("stadiums.id"), nullable=False, index=True)
    serial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[CardSource] = mapped_column(
        Enum(CardSource, name="card_source_enum", create_type=False), nullable=False
    )
    source_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    stadium: Mapped["Stadium"] = relationship(lazy="joined")
