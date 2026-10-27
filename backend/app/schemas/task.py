from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TaskCategory, TaskConditionType
from app.schemas.badge import BadgeOut
from app.schemas.monetization import GrantedRewardsOut
from app.schemas.pack import PackOpenResult


class TaskDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str
    category: TaskCategory
    condition_type: TaskConditionType
    metric: Optional[str]
    target_value: int
    condition_params: Optional[dict]
    reward_coins: int
    reward_pack_id: Optional[int]
    reward_skill_code: Optional[str] = None
    reward_skill_tokens: int = 0
    channel_username: Optional[str]
    channel_chat_id: Optional[int]
    invite_link: Optional[str]
    is_active: bool
    sort_order: int
    period: str = "daily"
    points: int = 20
    route: Optional[str] = None
    is_required: bool = False


class TaskDefinitionStatsOut(TaskDefinitionOut):
    # Distinct users who have completed / claimed this task right now. For
    # one-shot "premium" tasks this is a stable lifetime count. For
    # repeatable "regular" tasks it's a live snapshot only — task_service
    # resets completed_at/reward_claimed to null on each slot refill, so a
    # regular task's count can drop back down once users' slots rotate.
    completed_count: int
    claimed_count: int


class TaskDefinitionCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    category: TaskCategory = TaskCategory.regular
    condition_type: TaskConditionType
    metric: Optional[str] = None
    target_value: int = Field(default=1, ge=0)
    condition_params: Optional[dict] = None
    reward_coins: int = Field(default=0, ge=0)
    reward_pack_id: Optional[int] = None
    reward_skill_code: Optional[str] = None
    reward_skill_tokens: int = Field(default=0, ge=0, le=100)
    channel_username: Optional[str] = None
    channel_chat_id: Optional[int] = None
    invite_link: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0
    period: str = Field(default="daily", pattern="^(daily|weekly)$")
    points: int = Field(default=20, ge=0, le=1000)
    route: Optional[str] = Field(default=None, max_length=64)
    is_required: bool = False


class TaskDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[TaskCategory] = None
    condition_type: Optional[TaskConditionType] = None
    metric: Optional[str] = None
    target_value: Optional[int] = Field(default=None, ge=0)
    condition_params: Optional[dict] = None
    reward_coins: Optional[int] = Field(default=None, ge=0)
    reward_pack_id: Optional[int] = None
    reward_skill_code: Optional[str] = None
    reward_skill_tokens: Optional[int] = Field(default=None, ge=0, le=100)
    channel_username: Optional[str] = None
    channel_chat_id: Optional[int] = None
    invite_link: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    period: Optional[str] = Field(default=None, pattern="^(daily|weekly)$")
    points: Optional[int] = Field(default=None, ge=0, le=1000)
    route: Optional[str] = Field(default=None, max_length=64)
    is_required: Optional[bool] = None


class TaskOut(BaseModel):
    user_task_id: int
    code: str
    name: str
    description: str
    category: TaskCategory
    reward_coins: int
    reward_pack_name: Optional[str] = None
    reward_skill_code: Optional[str] = None
    reward_skill_tokens: int = 0
    channel_username: Optional[str] = None
    invite_link: Optional[str] = None
    progress: int
    target_value: int
    is_completed: bool
    is_claimed: bool
    period: str = "daily"
    points: int = 0
    # Where «Играть →» leads (a Mini App path), None = nowhere to go.
    route: Optional[str] = None
    is_required: bool = False


class TaskChestOut(BaseModel):
    index: int
    points: int
    coins: int = 0
    card_rarity: Optional[str] = None
    pack_id: Optional[int] = None
    is_claimed: bool
    is_available: bool


class TaskTrackOut(BaseModel):
    period_key: str
    points: int
    max_points: int
    chests: list[TaskChestOut]
    resets_at: datetime


class TaskListOut(BaseModel):
    # `regular` = today's set (kept under its old name for older clients).
    regular: list[TaskOut]
    weekly: list[TaskOut] = []
    premium: list[TaskOut]
    daily_track: Optional[TaskTrackOut] = None
    weekly_track: Optional[TaskTrackOut] = None
    rerolls_left: int = 0
    # The badge every required subscription earns (shown on the «Обязательно» banner).
    required_badge: Optional[BadgeOut] = None


class PremiumCoinsBackfillOut(BaseModel):
    definitions_updated: int
    users_credited: int


class GrantedSkillTokensOut(BaseModel):
    skill_code: str
    quantity: int


class TaskClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
    granted_skill_tokens: Optional[GrantedSkillTokensOut] = None
    granted_pack: Optional[PackOpenResult] = None
    refilled_task: Optional[TaskOut] = None
    points_added: int = 0
    # «Свой в клубе», when this claim completed the last required subscription.
    granted_badge: Optional[BadgeOut] = None


class TaskChestClaimOut(BaseModel):
    rewards: GrantedRewardsOut
    new_balance: int


class TaskRerollOut(BaseModel):
    task: TaskOut
    rerolls_left: int
