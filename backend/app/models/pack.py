from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import Rarity
from app.models.mixins import TimestampMixin


class Pack(TimestampMixin, Base):
    __tablename__ = "packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    card_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    guaranteed_min_rarity: Mapped[Optional[Rarity]] = mapped_column(
        Enum(Rarity, name="rarity_enum"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    purchase_limit_per_user: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rarity_probabilities: Mapped[list["PackRarityProbability"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan"
    )


class PackRarityProbability(Base):
    __tablename__ = "pack_rarity_probabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id", ondelete="CASCADE"), nullable=False, index=True)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False)
    probability: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)

    pack: Mapped["Pack"] = relationship(back_populates="rarity_probabilities")

    __table_args__ = (UniqueConstraint("pack_id", "rarity", name="uq_pack_rarity"),)


class PackOpening(Base):
    __tablename__ = "pack_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id", ondelete="RESTRICT"), nullable=False, index=True)
    price_paid: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cards: Mapped[list["PackOpeningCard"]] = relationship(back_populates="opening", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_pack_opening_idem"),)


class PackOpeningCard(Base):
    __tablename__ = "pack_opening_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opening_id: Mapped[int] = mapped_column(
        ForeignKey("pack_openings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_card_id: Mapped[int] = mapped_column(
        ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_new_player: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    opening: Mapped["PackOpening"] = relationship(back_populates="cards")
