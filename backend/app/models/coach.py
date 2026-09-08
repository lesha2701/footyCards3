from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CoachBoostType, Rarity
from app.models.mixins import TimestampMixin


class Coach(TimestampMixin, Base):
    __tablename__ = "coaches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity, name="rarity_enum"), nullable=False, index=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quick_sell_price: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Separate from is_active, same convention as Player.is_pack_droppable:
    # a coach can stay active (visible, usable) while excluded from new
    # pack drops once a coach pack exists in a later phase.
    is_pack_droppable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Unused until the pack/acquisition phases exist — reserved now so the
    # migration that introduces UserCoachCard/ClubCoachCard doesn't also
    # need to alter this table. Mirrors Player.next_serial_number's own
    # atomic-per-template-serial pattern (services/card_creation.py).
    next_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_club_serial_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    boosts: Mapped[list["CoachBoost"]] = relationship(back_populates="coach", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("rarity != 'diamond'", name="ck_coaches_rarity_not_diamond"),
    )


class CoachBoost(Base):
    __tablename__ = "coach_boosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coaches.id", ondelete="CASCADE"), nullable=False, index=True)
    # CoachBoostType's member names (ATTACK_CENTRAL) differ from their values
    # (attack_central) — every other enum in this codebase has matching
    # name/value pairs, which is why this is the only column that needs
    # values_callable. Without it, SQLAlchemy binds/reads native enums by
    # member .name by default, which doesn't match the lowercase labels the
    # migration actually created in Postgres (LookupError on every read).
    boost_type: Mapped[CoachBoostType] = mapped_column(
        Enum(CoachBoostType, name="coach_boost_type_enum", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    magnitude: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)

    coach: Mapped["Coach"] = relationship(back_populates="boosts")

    __table_args__ = (
        UniqueConstraint("coach_id", "boost_type", name="uq_coach_boost_type_once"),
    )
