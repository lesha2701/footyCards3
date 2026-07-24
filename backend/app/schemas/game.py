from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MemoryStartOut(BaseModel):
    session_id: int
    round_number: int
    sequence: list[str]
    reveal_ms: int


class MemorySubmitRequest(BaseModel):
    answer: list[str]


class MemorySubmitOut(BaseModel):
    correct: bool
    session_id: int
    score: int
    status: str
    next_round: Optional[MemoryStartOut] = None


class MemoryClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
    new_best_score: bool
    best_score: int


class MemoryLeaderboardEntry(BaseModel):
    user_id: int
    display_name: str
    avatar_url: Optional[str]
    best_score: int


# --- Saboteur ---

class SaboteurStartRequest(BaseModel):
    bomb_count: int = 1


class SaboteurStartOut(BaseModel):
    session_id: int
    grid_size: int
    bomb_count: int


class SaboteurRevealRequest(BaseModel):
    cell_index: int


class SaboteurRevealOut(BaseModel):
    is_bomb: bool
    session_id: int
    score: int
    status: str
    reward_coins: Optional[int] = None


class SaboteurClaimOut(BaseModel):
    reward_coins: int
    new_balance: int


# --- Penalty ---

class PenaltyStartRequest(BaseModel):
    user_card_id: int


class PenaltyStartOut(BaseModel):
    session_id: int
    player_rating: int
    first_kicker: str


class PenaltyKickRequest(BaseModel):
    direction: str


class PenaltyKickOut(BaseModel):
    session_id: int
    kicker: str
    outcome: str
    player_direction: Optional[str] = None
    bot_direction: str
    player_score: int
    bot_score: int
    next_kicker: Optional[str] = None
    is_finished: bool
    result: Optional[str] = None


class PenaltyClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
    result: str


# --- Free Kick ---

class FreeKickStartRequest(BaseModel):
    user_card_id: int


class FreeKickNextKickOut(BaseModel):
    kick_index: int
    period_ms: int
    start_ts: datetime
    half_width: float


class FreeKickStartOut(BaseModel):
    session_id: int
    kick: FreeKickNextKickOut


class FreeKickKickRequest(BaseModel):
    elapsed_ms: int


class FreeKickKickOut(BaseModel):
    tier: str
    coins_this_kick: int
    total_coins: int
    is_finished: bool
    next_kick: Optional[FreeKickNextKickOut] = None


class FreeKickClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
