from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ClubRole


class ClubPostOut(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    avatar_url: Optional[str]
    # Null once the author has left the club.
    role: Optional[ClubRole]
    text: str
    is_announcement: bool
    is_pinned: bool
    created_at: datetime
    can_delete: bool


class ClubWallOut(BaseModel):
    posts: list[ClubPostOut]
    can_announce: bool
    can_pin: bool
    announce_cooldown_seconds: int


class ClubPostIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    announce: bool = False
