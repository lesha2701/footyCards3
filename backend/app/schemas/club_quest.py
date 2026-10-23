from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.monetization import RewardBundleIn, RewardBundleOut

QuestMetric = Literal["games", "packs", "tasks"]


class ClubQuestOut(BaseModel):
    id: int
    title: str
    metric: QuestMetric
    target: int
    progress: int
    completed: bool
    reward_budget: int
    # Per member, claimed in the club shop's rewards list.
    reward: RewardBundleOut


class ClubQuestMemberOut(BaseModel):
    user_id: int
    name: str
    games: int
    packs: int
    tasks: int


class ClubQuestsOut(BaseModel):
    enabled: bool
    week_start: date
    ends_at: datetime
    quests: list[ClubQuestOut]
    members: list[ClubQuestMemberOut]


class ClubQuestAdminOut(BaseModel):
    id: int
    title: str
    metric: QuestMetric
    target_per_member: int
    reward_budget: int
    reward: RewardBundleIn
    is_active: bool
    sort_order: int


class ClubQuestIn(BaseModel):
    title: str = Field(min_length=1, max_length=96)
    metric: QuestMetric
    target_per_member: int = Field(ge=1, le=1000)
    reward_budget: int = Field(default=0, ge=0, le=10_000_000)
    reward: RewardBundleIn
    is_active: bool = True
    sort_order: int = 0
