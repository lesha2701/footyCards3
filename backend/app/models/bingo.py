from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import BingoGoalType
from app.models.mixins import TimestampMixin


class BingoState(Base):
    """Singleton (id=1) — whether the weekly Bingo event is turned on, and
    the epoch every week's boundaries are computed from. `started_at` is set
    once, the first time an admin enables the event, and never moves again —
    week N always runs [started_at + (N-1)*7d, started_at + N*7d)."""

    __tablename__ = "bingo_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class BingoGoalDefinition(TimestampMixin, Base):
    """Admin-tunable list of weekly goals. Editing target_value/is_active or
    adding a row here never touches an already-running week — see
    BingoWeekGoal, which snapshots this at the moment each new week starts.
    At most one active row per goal_type (enforced in bingo_service)."""

    __tablename__ = "bingo_goal_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_type: Mapped[BingoGoalType] = mapped_column(Enum(BingoGoalType, name="bingo_goal_type_enum"), nullable=False)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BingoWeek(Base):
    __tablename__ = "bingo_weeks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # True once this week's outcome has been decided (reward distributed, or
    # goals fell short) — set exactly once, guarded by a row lock, so a sweep
    # racing to resolve the same overdue week from two requests can't double-pay.
    reward_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    all_goals_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("week_number", name="uq_bingo_week_number"),)


class BingoWeekGoal(Base):
    """A frozen-at-week-start copy of one BingoGoalDefinition, plus the live
    counter every hook increments. This snapshot is what makes admin edits
    to BingoGoalDefinition apply "next week only" — nothing here changes
    except current_value once the row exists."""

    __tablename__ = "bingo_week_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("bingo_weeks.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_type: Mapped[BingoGoalType] = mapped_column(Enum(BingoGoalType, name="bingo_goal_type_enum"), nullable=False)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("week_id", "goal_type", name="uq_bingo_week_goal"),)


class BingoWeekReward(Base):
    """Audit trail + idempotency guard: one row per user actually credited
    for a completed week (same role as CardUpgradeAttempt)."""

    __tablename__ = "bingo_week_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("bingo_weeks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    coins_granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pack_id_granted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("week_id", "user_id", name="uq_bingo_week_reward"),)
