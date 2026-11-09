from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchDifficulty, MatchResult, MatchStatus
from app.schemas.game import FreeKick3DShotRequest, Penalty3DDive


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
    image_path: Optional[str] = None
    rarity: Optional[str] = None


class MatchDuelActorOut(BaseModel):
    name: str
    rating: int
    position: str
    image_path: Optional[str] = None
    rarity: Optional[str] = None


class MatchOptionOut(BaseModel):
    """One choice of a moment: who plays it, against whom and what it risks."""
    action: str
    me: MatchDuelActorOut
    vs: MatchDuelActorOut
    risk: Literal["low", "mid", "high"]
    note: str


class MatchPendingMomentOut(BaseModel):
    seq: int
    team: str
    kind: Literal["attack", "defense", "breakaway", "halftime", "late_call", "penalty"]
    shot_type: str
    description: str
    actions: list[str]
    actors: dict[str, MatchActorOut]
    options: list[MatchOptionOut] = []
    # Seconds on the moment's clock (None: no clock, e.g. a penalty scene).
    seconds: Optional[int] = None
    # Penalty scene: the shared seed, the taker's rating, the taker.
    seed: Optional[int] = None
    rating: Optional[int] = None
    taker: Optional[MatchDuelActorOut] = None


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
    # This match was already running: show it as it stands, don't replay it.
    resumed: bool = False


class MatchHistoryItemOut(BaseModel):
    """A row of the history; the events load when the row is opened."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    opponent_name: str
    user_score: int
    opponent_score: int
    result: Optional[MatchResult] = None
    reward_coins: int
    created_at: datetime
    ladder: Optional[dict] = None


class StartMatchRequest(BaseModel):
    difficulty: MatchDifficulty = MatchDifficulty.medium
    mode: Literal["ladder", "cup"] = "ladder"


class MatchActionRequest(BaseModel):
    # "auto": the clock ran out or the player skips — the server picks.
    action: Literal[
        "shoot", "pass", "dribble", "tackle", "block", "keeper", "strike",
        "keep_style", "change_style", "all_in", "hold", "kick", "dive", "auto",
    ]
    expected_seq: Optional[int] = None
    # change_style: the new style; kick / dive: the swipe of the 3D scene.
    style: Optional[str] = None
    swipe: Optional[FreeKick3DShotRequest] = None
    dive: Optional[Penalty3DDive] = None


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
    # Matches left this hour; 0 + retry_after_seconds = the wait.
    hourly_limit: int = 0
    hourly_left: int = 0
    retry_after_seconds: int = 0
    # Attacks on your squad you haven't read yet.
    defense_unread: int = 0
    cup: Optional[dict] = None


class ArenaDefenseItemOut(BaseModel):
    """Someone played against your squad: the result is from your side."""
    match_id: int
    attacker_name: str
    attacker_avatar_url: Optional[str] = None
    result: MatchResult
    my_score: int
    their_score: int
    created_at: datetime
    can_revenge: bool


class ArenaLineCompareOut(BaseModel):
    key: str
    label: str
    user: int
    opponent: int


class ArenaKeyDuelOut(BaseModel):
    """Your best outfield card and whoever faces him; a bot has a line, not a card."""
    me: MatchDuelActorOut
    vs: MatchDuelActorOut


class ArenaPreviewOut(BaseModel):
    opponent_name: str
    opponent_avatar_url: Optional[str] = None
    opponent_is_bot: bool
    opponent_points: int
    opponent_division: int
    opponent_strength: int
    # A tendency, not a fact: the real style is revealed at kickoff.
    opponent_style_hint: str
    opponent_formation: str = "4-3-3"
    user_strength: int
    user_style: str
    user_formation: str = "4-3-3"
    # W/D/L of your matches against this opponent; None: first meeting.
    head_to_head: Optional[dict[str, int]] = None
    # This match's goal (shown before kickoff, paid at the whistle).
    goal_text: Optional[str] = None
    goal_bonus_coins: int = 0
    revenge: bool = False
    lines: list[ArenaLineCompareOut]
    key_duel: Optional[ArenaKeyDuelOut] = None
    # ≈ % for an average player (scripts/simulate_arena_balance.py).
    chances: dict[str, int]
    # Arena points for a win / draw / loss.
    points_at_stake: dict[str, int]
    division: ArenaDivisionOut
    # What coaches / stadiums take off each side's lines (already applied
    # to the strengths and lines above): {"FWD": 4, …}.
    opponent_malus: dict[str, int] = {}
    user_malus: dict[str, int] = {}


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
