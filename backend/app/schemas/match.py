from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchDifficulty, MatchResult


class MatchEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minute: int
    event_type: str
    team: str
    description: str


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opponent_name: str
    difficulty: MatchDifficulty
    user_team_strength: int
    opponent_team_strength: int
    user_score: int
    opponent_score: int
    result: MatchResult
    reward_coins: int
    rating_delta: int
    created_at: datetime
    events: list[MatchEventOut] = []


class StartMatchRequest(BaseModel):
    difficulty: MatchDifficulty = MatchDifficulty.medium


class ArenaStatsOut(BaseModel):
    matches_won: int
    matches_drawn: int
    matches_lost: int
    arena_rating: int
    match_energy: int
    max_energy: int


class ArenaLeaderboardEntry(BaseModel):
    user_id: int
    display_name: str
    avatar_url: Optional[str]
    arena_rating: int
    matches_won: int
