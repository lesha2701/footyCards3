from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class MyPlayerSponsorContract(Base):
    """«Спонсор» of «Мой игрок» for one week (my_player_extras): the brand
    picked from the week's three offers, goal progress and what was paid.
    One contract a week (the unique row also stops a double sign)."""

    __tablename__ = "my_player_sponsor_contracts"
    __table_args__ = (UniqueConstraint("user_id", "week", name="uq_my_player_sponsor_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # ISO week, local time ("2026-W44").
    week: Mapped[str] = mapped_column(String(8), nullable=False)
    brand: Mapped[str] = mapped_column(String(32), nullable=False)
    # The brand's goal codes frozen at signing (the first three; the fourth
    # counts only with premium) — admin edits don't move a running contract.
    goals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Premium contract (Telegram Stars): the fourth goal and more coins.
    premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # {goal_code: count this week}
    progress: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {goal_code | "_bonus": coins paid} — premium tops up what was paid.
    paid: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MyPlayerGift(Base):
    """A gift to a friend's «Мой игрок», paid with Telegram Stars by the
    sender: a training, a style item or «Карьера Pro» days. The count of
    gifts sent makes the sender a «Меценат»."""

    __tablename__ = "my_player_gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # training | pro | cosmetic
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MyPlayerEdition(Base):
    """A numbered copy of a limited «Мой игрок» style item (GameConfig
    .my_player_limited_supply): number = order of sale, one per owner."""

    __tablename__ = "my_player_editions"
    __table_args__ = (
        UniqueConstraint("code", "number", name="uq_my_player_edition_number"),
        UniqueConstraint("code", "user_id", name="uq_my_player_edition_owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
