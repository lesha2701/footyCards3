import enum
from typing import Optional

from pydantic import BaseModel

from app.schemas.badge import BadgeOut


class RankingMetric(str, enum.Enum):
    arena_rating = "arena_rating"
    matches_won = "matches_won"
    cards_count = "cards_count"
    unique_players = "unique_players"
    referral_count = "referral_count"
    tactics_rating = "tactics_rating"


class RankingEntry(BaseModel):
    rank: int
    user_id: int
    display_name: str
    avatar_url: Optional[str]
    value: int
    active_badge: Optional[BadgeOut] = None


class RankingOut(BaseModel):
    metric: RankingMetric
    top: list[RankingEntry]
    me: Optional[RankingEntry] = None
