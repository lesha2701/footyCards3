from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TaskCategory, TaskConditionType
from app.schemas.card import UserCardOut


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
    channel_username: Optional[str]
    channel_chat_id: Optional[int]
    invite_link: Optional[str]
    is_active: bool
    sort_order: int


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
    channel_username: Optional[str] = None
    channel_chat_id: Optional[int] = None
    invite_link: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


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
    channel_username: Optional[str] = None
    channel_chat_id: Optional[int] = None
    invite_link: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class TaskOut(BaseModel):
    user_task_id: int
    code: str
    name: str
    description: str
    category: TaskCategory
    reward_coins: int
    reward_pack_name: Optional[str] = None
    channel_username: Optional[str] = None
    invite_link: Optional[str] = None
    progress: int
    target_value: int
    is_completed: bool
    is_claimed: bool


class TaskListOut(BaseModel):
    regular: list[TaskOut]
    premium: list[TaskOut]


class TaskClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
    granted_pack_name: Optional[str] = None
    granted_card: Optional[UserCardOut] = None
    refilled_task: Optional[TaskOut] = None
