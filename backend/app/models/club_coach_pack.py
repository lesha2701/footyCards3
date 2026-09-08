from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Rarity
from app.models.mixins import TimestampMixin


class ClubCoachPack(TimestampMixin, Base):
    __tablename__ = "club_coach_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    card_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    guaranteed_min_rarity: Mapped[Optional[Rarity]] = mapped_column(SAEnum(Rarity, name="rarity_enum"), nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rarity_probabilities: Mapped[list["ClubCoachPackRarityProbability"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan"
    )


class ClubCoachPackRarityProbability(Base):
    __tablename__ = "club_coach_pack_rarity_probabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_coach_pack_id: Mapped[int] = mapped_column(ForeignKey("club_coach_packs.id", ondelete="CASCADE"), nullable=False)
    rarity: Mapped[Rarity] = mapped_column(SAEnum(Rarity, name="rarity_enum"), nullable=False)
    probability: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)

    pack: Mapped["ClubCoachPack"] = relationship(back_populates="rarity_probabilities")

    __table_args__ = (UniqueConstraint("club_coach_pack_id", "rarity", name="uq_club_coach_pack_rarity_once"),)
