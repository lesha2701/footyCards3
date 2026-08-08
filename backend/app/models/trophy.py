from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class TrophyDefinition(TimestampMixin, Base):
    """An admin-defined trophy. Deliberately its own lightweight system, not
    a Player/UserCard — trophies don't drop from packs, don't count toward
    collection stats, and can't be traded. Right now every trophy is granted
    by an admin (see UserTrophy.granted_by_admin_id); auto-granting on
    season completion is planned but not wired up yet."""

    __tablename__ = "trophy_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(16), nullable=False, default="🏆")
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ORM-level cascade (not just the DB-level ondelete="CASCADE" on the FK
    # below) so deleting a definition always cleans up every grant of it
    # through SQLAlchemy's own unit-of-work, regardless of whether the
    # connected DB actually enforces FK constraints (SQLite doesn't unless
    # PRAGMA foreign_keys=ON, which the test suite doesn't set).
    grants: Mapped[list["UserTrophy"]] = relationship(back_populates="trophy", cascade="all, delete-orphan")


class UserTrophy(Base):
    """A trophy granted to a user. Ownership is permanent (no unequip, unlike
    Badge) — it's a display-only trophy case entry, not something worn next
    to the name. `message` is the admin's personal note shown alongside it
    (e.g. "За вклад в развитие сообщества — спасибо!")."""

    __tablename__ = "user_trophies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    trophy_definition_id: Mapped[int] = mapped_column(
        ForeignKey("trophy_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_by_admin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    trophy: Mapped["TrophyDefinition"] = relationship(back_populates="grants", lazy="joined")
