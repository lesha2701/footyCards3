from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class CardCollection(TimestampMixin, Base):
    """A thematic grouping of Player designs (e.g. "World Cup 2026",
    "Legends"). Distinct from the player's own owned-cards screen
    ("Карточки" / CollectionPage.tsx) — this is an admin-managed catalog
    concept, not a per-user collection."""

    __tablename__ = "card_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("packs.id", ondelete="SET NULL"), nullable=True
    )

    players: Mapped[list["Player"]] = relationship(back_populates="collection")


class UserCollectionReward(Base):
    """One row per (user, collection) once the user owns at least one copy
    of every active player in that collection — gates the completion reward
    to fire exactly once per user per collection."""

    __tablename__ = "user_collection_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("card_collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("packs.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "collection_id", name="uq_user_collection_rewards_user_collection"),
    )
