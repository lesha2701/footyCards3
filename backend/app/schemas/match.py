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
    # «Академия»: static talents applied at kickoff, and the experience
    # the path cards earned once the match is over.
    talent_notes: Optional[list[dict]] = None
    path_progress: Optional[list[dict]] = None
    # Card Arena divisions/styles: the styles and chances frozen at kickoff,
    # the points movement and the «Разбор матча» once it's over.
    arena: Optional[dict] = None
    ladder: Optional[dict] = None
    report: Optional[dict] = None


class StartMatchRequest(BaseModel):
    difficulty: MatchDifficulty = MatchDifficulty.medium


class MatchActionRequest(BaseModel):
    action: Literal["shoot", "pass", "tackle", "block", "keeper", "strike"]
    expected_seq: Optional[int] = None


class ArenaDivisionOut(BaseModel):
    division: int
    total_divisions: int
    points: int
    min_points: int
    next_min_points: Optional[int] = None
    shield_matches: int = 0
    coin_pct: int = 100
    next_reward_coins: Optional[int] = None


class ArenaStatsOut(BaseModel):
    matches_won: int
    matches_drawn: int
    matches_lost: int
    arena_rating: int
    # Place by arena points (None before the first division match).
    arena_rank: Optional[int] = None
    division: Optional[ArenaDivisionOut] = None


class ArenaLineCompareOut(BaseModel):
    key: str
    label: str
    user: int
    opponent: int


class ArenaPreviewOut(BaseModel):
    opponent_name: str
    opponent_avatar_url: Optional[str] = None
    opponent_is_bot: bool
    opponent_points: int
    opponent_division: int
    opponent_strength: int
    opponent_style: str
    opponent_formation: str = "4-3-3"
    user_strength: int
    user_style: str
    user_formation: str = "4-3-3"
    matchup: Literal["win", "loss", "neutral"]
    matchup_bonus_pct: int
    matchup_text: str
    lines: list[ArenaLineCompareOut]
    # ≈ % for an average player (scripts/simulate_arena_balance.py).
    chances: dict[str, int]
    # Arena points for a win / draw / loss.
    points_at_stake: dict[str, int]
    division: ArenaDivisionOut


class ArenaLeaderboardEntry(BaseModel):
    user_id: int
    display_name: str
    avatar_url: Optional[str]
    arena_rating: int
    arena_points: int = 0
    division: int = 1
    matches_won: int
    matches_drawn: int
    matches_lost: int
    goal_difference: int
    points: int
