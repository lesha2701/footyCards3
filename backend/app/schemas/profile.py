from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.player import PlayerOut


class ProfilePublicOut(BaseModel):
    id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    level: int
    arena_rating: int
    arena_rank: int
    matches_won: int
    matches_drawn: int
    matches_lost: int
    memory_best_score: int
    unique_cards: int
    total_cards: int
    rarest_card: Optional[PlayerOut]
    packs_opened: int
    referral_count: int


class ProfilePrivateOut(ProfilePublicOut):
    telegram_id: int
    balance: int
    experience: int
    is_admin: bool
    telegram_bot_username: str
