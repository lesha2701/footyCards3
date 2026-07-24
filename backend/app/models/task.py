from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TaskCategory, TaskConditionType
from app.models.mixins import TimestampMixin, utcnow


class TaskDefinition(TimestampMixin, Base):
    __tablename__ = "task_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    category: Mapped[TaskCategory] = mapped_column(
        Enum(TaskCategory, name="task_category_enum"), default=TaskCategory.regular, nullable=False
    )
    condition_type: Mapped[TaskConditionType] = mapped_column(
        Enum(TaskConditionType, name="task_condition_type_enum"), nullable=False
    )
    metric: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    condition_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("packs.id", ondelete="SET NULL"), nullable=True
    )
    channel_username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    channel_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    invite_link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserTask(Base):
    __tablename__ = "user_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_definition_id: Mapped[int] = mapped_column(
        ForeignKey("task_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "task_definition_id", name="uq_user_task"),
        Index(
            "uq_user_task_slot", "user_id", "slot_index", unique=True,
            postgresql_where=text("slot_index IS NOT NULL"),
        ),
    )
