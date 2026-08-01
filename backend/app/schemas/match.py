from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchDifficulty, MatchResult, MatchStatus


class MatchEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minute: int
    event_type: str
    team: str
    description: str
    payload: Optional[dict] = None


class MatchPendingShotOut(BaseModel):
    team: str
    shot_type: str
    seq: int


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opponent_name: str
    difficulty: MatchDifficulty
    user_team_strength: int
    opponent_team_strength: int
    user_score: int
    opponent_score: int
    status: MatchStatus
    result: Optional[MatchResult] = None
    reward_coins: int
    rating_delta: int
    created_at: datetime
    events: list[MatchEventOut] = []
    pending_shot: Optional[MatchPendingShotOut] = None


class StartMatchRequest(BaseModel):
    difficulty: MatchDifficulty = MatchDifficulty.medium


class ShootRequest(BaseModel):
    direction: Optional[Literal["left", "center", "right"]] = None
    expected_seq: Optional[int] = None


class ArenaStatsOut(BaseModel):
    matches_won: int
    matches_drawn: int
    matches_lost: int
    arena_rating: int
    arena_rank: Optional[int] = None


class ArenaLeaderboardEntry(BaseModel):
    user_id: int
    display_name: str
    avatar_url: Optional[str]
    arena_rating: int
    matches_won: int
    matches_drawn: int
    matches_lost: int
    goal_difference: int
    points: int
