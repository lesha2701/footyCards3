from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class StarsPatronAward(Base):
    """«Покровитель недели» (services/stars_patron_service.py): the week's top
    Stars buyers. Place 0 is the marker that the week was settled (also when
    nobody qualified), so the unique key makes the settlement run once."""

    __tablename__ = "stars_patron_awards"
    __table_args__ = (UniqueConstraint("week_start", "place", name="uq_stars_patron_week_place"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    place: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
