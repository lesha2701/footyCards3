from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.schemas.card import UserCardOut


class DailyRewardDayOut(BaseModel):
    day: int
    coins: int
    free_pack_name: Optional[str] = None
    grants_random_card: bool = False
    is_claimed: bool = False
    is_today: bool = False


class DailyRewardCalendarOut(BaseModel):
    current_streak: int
    already_claimed_today: bool
    days: list[DailyRewardDayOut]


class DailyRewardClaimOut(BaseModel):
    streak_day: int
    coins_awarded: int
    new_balance: int
    granted_card: Optional[UserCardOut] = None
    granted_pack_name: Optional[str] = None


class DailyRewardOptionIn(BaseModel):
    day: int
    option_index: int
    coins: int
    free_pack_slug: Optional[str] = None
    grants_random_card: bool = False


class DailyRewardOptionOut(DailyRewardOptionIn):
    id: int

    model_config = {"from_attributes": True}


class DailyRewardOptionsUpdate(BaseModel):
    options: list[DailyRewardOptionIn]
