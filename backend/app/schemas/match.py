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


class MatchActorOut(BaseModel):
    user_card_id: int
    player_id: int
    name: str
    rating: int
    position: str


class MatchPendingMomentOut(BaseModel):
    seq: int
    team: str
    kind: Literal["attack", "defense", "breakaway"]
    shot_type: str
    description: str
    actions: list[Literal["shoot", "pass", "tackle", "block", "keeper", "strike"]]
    actors: dict[str, MatchActorOut]


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
    pending_moment: Optional[MatchPendingMomentOut] = None


class StartMatchRequest(BaseModel):
    difficulty: MatchDifficulty = MatchDifficulty.medium


class MatchActionRequest(BaseModel):
    action: Literal["shoot", "pass", "tackle", "block", "keeper", "strike"]
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
