from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ClubStadiumCardSource
from app.models.mixins import utcnow


class ClubStadiumCard(Base):
    __tablename__ = "club_stadium_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(
        ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stadium_id: Mapped[int] = mapped_column(ForeignKey("stadiums.id"), nullable=False, index=True)
    serial_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[ClubStadiumCardSource] = mapped_column(
        Enum(ClubStadiumCardSource, name="club_stadium_card_source_enum"), nullable=False
    )
    source_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    stadium: Mapped["Stadium"] = relationship(lazy="joined")
