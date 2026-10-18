from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ClubQuestTemplate(Base):
    """«Задания недели» клуба (club_quest_service): every active template is
    a quest for every club each league week. The goal scales with the club:
    target = target_per_member x member count. On completion the club budget
    gets `reward_budget` and every member claims the reward bundle."""
    __tablename__ = "club_quest_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(96), nullable=False)
    # "games" | "packs" | "tasks" — the same activity the club league counts.
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    target_per_member: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    reward_card_rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reward_badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="SET NULL"), nullable=True)
    reward_cosmetic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ClubQuestCompletion(Base):
    __tablename__ = "club_quest_completions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("club_quest_templates.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    target: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("club_id", "template_id", "week_start", name="uq_club_quest_completion_once"),
    )
