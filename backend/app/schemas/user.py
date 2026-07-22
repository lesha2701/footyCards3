from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserPublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    avatar_url: Optional[str]
    level: int
    arena_rating: int
    created_at: datetime


class UserMeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    avatar_url: Optional[str]
    balance: int
    is_admin: bool
    level: int
    experience: int
    arena_rating: int
    matches_won: int
    matches_drawn: int
    matches_lost: int
    memory_best_score: int
    match_energy: int
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserMeOut
    admin_token: Optional[str] = None
