from typing import Optional

from pydantic import BaseModel

from app.models.enums import ClubRole


class ClubMemberActivityOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    role: ClubRole
    games_played: int
    daily_rewards_claimed: int
