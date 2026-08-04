from datetime import datetime
from typing import Optional

from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class Badge(TimestampMixin, Base):
    """An admin-defined flair, granted to players as a configurable reward on
    a Stars pack (see Pack.badge_id) and displayed next to their name
    wherever a UserPublicOut-shaped identity is shown (profile, rankings,
    trades). `icon` is a short emoji/text glyph fallback shown when no
    `image_path` has been uploaded."""

    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    icon: Mapped[str] = mapped_column(String(16), nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserBadge(Base):
    """A badge a user has been granted. Ownership is permanent even if the
    badge is later deactivated or unequipped; `User.active_badge_id` controls
    which owned badge (if any) is currently displayed."""

    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    badge: Mapped["Badge"] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)
