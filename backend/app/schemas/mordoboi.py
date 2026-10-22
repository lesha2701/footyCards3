from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.enums import MatchResult, MordoboiMatchStatus, MordoboiOpponentType

MordoboiAction = Literal["jab", "hook", "uppercut", "block", "dodge"]


class MordoboiCardOut(BaseModel):
    """Snapshot of the card behind a boxer — taken at match start."""

    user_card_id: Optional[int] = None
    player_id: int
    display_name: str
    position: str
    image_path: Optional[str] = None
    rarity: str
    rating: int


class MordoboiBoxerStatsOut(BaseModel):
    power: int
    speed: int
    guard: int
    max_hp: int
    max_stamina: int


class MordoboiBoxerOptionOut(BaseModel):
    card: MordoboiCardOut
    stats: MordoboiBoxerStatsOut


class MordoboiBoxerOut(BaseModel):
    """The saved boxer plus every card that could box, strongest first."""

    selected: Optional[MordoboiBoxerOptionOut] = None
    options: list[MordoboiBoxerOptionOut]


class MordoboiBoxerSetRequest(BaseModel):
    user_card_id: int


class MordoboiFighterOut(BaseModel):
    name: str
    card: Optional[MordoboiCardOut] = None
    power: int
    speed: int
    guard: int
    hp: int
    max_hp: int
    stamina: int
    max_stamina: int
    landed: int
    damage_dealt: int


class MordoboiExchangeOut(BaseModel):
    """One resolved exchange from the viewer's side: `mine_*` is the viewer."""

    n: int
    round: int
    exchange: int
    my_action: str
    opponent_action: str
    my_outcome: str
    opponent_outcome: str
    my_damage: int  # dealt by the viewer
    opponent_damage: int
    my_hp: int
    opponent_hp: int
    my_auto: bool = False
    opponent_auto: bool = False
    round_end: bool = False
    end: Optional[str] = None


class MordoboiScorecardOut(BaseModel):
    mine: int
    opponent: int


class MordoboiBrutalityOut(BaseModel):
    """A joke finisher the winner did after the bout."""

    by_me: bool
    style_key: str
    name: str
    emoji: str
    image_path: Optional[str] = None
    # Coins it added to the winner's reward.
    bonus_coins: int = 0
    # From the viewer's side: «надел ему труханы на голову» / «…тебе…».
    text: str


class MordoboiBrutalityRequest(BaseModel):
    cosmetic_id: int


class MordoboiMatchOut(BaseModel):
    id: int
    version: int
    opponent_type: MordoboiOpponentType
    opponent_name: str
    opponent_user_id: Optional[int] = None
    status: MordoboiMatchStatus
    viewer_side: Literal["user", "opponent"]
    difficulty: Optional[str] = None
    live: bool = False
    rounds: int
    exchanges_per_round: int
    round: int
    exchange: int
    me: Optional[MordoboiFighterOut] = None
    opponent: Optional[MordoboiFighterOut] = None
    # The viewer's own pick for the current exchange (never the opponent's).
    my_pick: Optional[str] = None
    opponent_ready: bool = False
    can_pick: bool = False
    available_actions: list[str] = []
    deadline: Optional[datetime] = None
    my_auto_moves: int = 0
    max_auto_moves: int = 0
    log: list[MordoboiExchangeOut] = []
    scorecards: list[MordoboiScorecardOut] = []
    result: Optional[MatchResult] = None
    win_reason: Optional[str] = None
    reward_coins: int = 0
    rating_delta: int = 0
    stake_coins: int = 0
    brutality: Optional[MordoboiBrutalityOut] = None
    # The viewer won and hasn't finished the opponent off yet.
    can_brutality: bool = False
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class MordoboiInfoOut(BaseModel):
    enabled: bool
    rounds: int
    exchanges_per_round: int
    base_hp: int
    reward_win: int
    reward_draw: int
    reward_loss: int
    reward_ko_bonus: int
    daily_limit: int
    rewarded_today: int
    easy_reward_pct: int
    move_timeout_hours: int
    live_move_seconds: int
    challenge_expiry_hours: int
    max_auto_moves: int
    # Rules numbers for the help screen (engine constants).
    stamina_cost: dict[str, int]
    damage: dict[str, int]


class MordoboiStatsOut(BaseModel):
    mordoboi_rating: int
    mordoboi_rank: Optional[int] = None


class MordoboiBotMatchRequest(BaseModel):
    difficulty: Literal["easy", "hard"] = "hard"


class MordoboiChallengeRequest(BaseModel):
    receiver_id: int


class MordoboiOpenChallengeRequest(BaseModel):
    stake_coins: int = 0


class MordoboiOpenChallengePreviewOut(BaseModel):
    id: int
    creator_name: str
    stake_coins: int
    status: MordoboiMatchStatus
    is_own_challenge: bool


class MordoboiPickRequest(BaseModel):
    action: MordoboiAction
    # The match version the client saw — a stale one gets 409 (unless it is
    # a replay of a pick already recorded, which returns the match as is).
    version: int


class MordoboiSearchStatusOut(BaseModel):
    status: Literal["not_searching", "searching", "matched", "timeout"]
    match_id: Optional[int] = None
