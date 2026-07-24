from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


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

    players: Mapped[list["Player"]] = relationship(back_populates="collection")
