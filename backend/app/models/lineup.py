from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class Lineup(TimestampMixin, Base):
    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # 1..5 — one of 5 fixed, always-present saved squads (see
    # lineup_service._ensure_templates). Not user-facing as a raw number;
    # the UI shows `name` and a 5-tab switcher.
    template_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Основной состав")
    formation: Mapped[str] = mapped_column(String(16), nullable=False, default="4-3-3")
    tactic: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_coach_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True
    )

    cards: Mapped[list["LineupCard"]] = relationship(back_populates="lineup", cascade="all, delete-orphan")
    user_coach_card: Mapped["UserCoachCard | None"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "template_index", name="uq_lineup_user_template"),
        # Enforces "at most one active lineup per user" at the DB level —
        # lineup_service._ensure_templates does a check-then-insert with no
        # row to lock when a template doesn't exist yet, so without this,
        # two concurrent first-time requests could both seed template_index=1
        # as active. Still valid with 5 templates: "at most one active among
        # a user's rows" is unchanged, just now among 5 instead of 1.
        Index(
            "uq_lineup_one_active_per_user", "user_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
    )


class LineupCard(Base):
    __tablename__ = "lineup_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lineup_id: Mapped[int] = mapped_column(ForeignKey("lineups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[int] = mapped_column(
        ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Formation slot code, e.g. "GK", "DEF1".."DEF4", "MID1".."MID3", "FWD1".."FWD3"
    slot_code: Mapped[str] = mapped_column(String(16), nullable=False)

    lineup: Mapped["Lineup"] = relationship(back_populates="cards")

    __table_args__ = (
        UniqueConstraint("lineup_id", "user_card_id", name="uq_lineup_card_once"),
        UniqueConstraint("lineup_id", "slot_code", name="uq_lineup_slot_once"),
    )
