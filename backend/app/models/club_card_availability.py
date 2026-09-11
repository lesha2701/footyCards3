from sqlalchemy import Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ClubCardAvailabilityReason


class ClubCardAvailability(Base):
    """A row only exists while a ClubCard is actually suspended
    (rounds_remaining > 0). Absence of a row = available. Delete the row
    once rounds_remaining reaches 0 rather than keeping it at 0."""

    __tablename__ = "club_card_availabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_card_id: Mapped[int] = mapped_column(ForeignKey("club_cards.id", ondelete="CASCADE"), unique=True, nullable=False)
    rounds_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[ClubCardAvailabilityReason] = mapped_column(
        Enum(ClubCardAvailabilityReason, name="club_card_availability_reason_enum"), nullable=False,
    )
