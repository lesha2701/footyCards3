from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClubDailyClaim(Base):
    __tablename__ = "club_daily_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("club_id", "user_id", "claim_date", name="uq_club_daily_claim_once_per_day"),)
