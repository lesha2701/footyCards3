import enum
from typing import Optional

from pydantic import BaseModel


class PlayerTournamentRankingMetric(str, enum.Enum):
    cups = "cups"
    stars = "stars"


class PlayerTournamentRankingEntry(BaseModel):
    rank: int
    user_id: int
    display_name: str
    value: int


class PlayerTournamentRankingOut(BaseModel):
    metric: PlayerTournamentRankingMetric
    top: list[PlayerTournamentRankingEntry]
    me: Optional[PlayerTournamentRankingEntry] = None
