from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.monetization import RewardBundleIn, RewardBundleOut


class ClubRewardOut(BaseModel):
    id: int
    source: str
    title: str
    reward: RewardBundleOut
    created_at: datetime
    expires_at: datetime


class ClubShopItemOut(BaseModel):
    id: int
    name: str
    description: str
    price: int
    weekly_limit: int
    bought_this_week: int
    reward: RewardBundleOut


class ClubShopOut(BaseModel):
    budget: int
    can_buy: bool
    member_count: int
    items: list[ClubShopItemOut]
    # Unclaimed rewards of the requester (from the shop, quests and wars).
    rewards: list[ClubRewardOut]


class ClubShopItemAdminOut(BaseModel):
    id: int
    name: str
    description: str
    price: int
    weekly_limit: int
    reward: RewardBundleIn
    is_active: bool
    sort_order: int


class ClubShopItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=256)
    price: int = Field(ge=1, le=10_000_000)
    weekly_limit: int = Field(default=1, ge=1, le=50)
    reward: RewardBundleIn
    is_active: bool = True
    sort_order: int = 0


class ClubRewardsCountOut(BaseModel):
    unclaimed: int
    first: Optional[ClubRewardOut] = None
