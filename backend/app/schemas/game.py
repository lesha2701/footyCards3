from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.player import PlayerOut


class MemoryStartOut(BaseModel):
    session_id: int
    round_number: int
    sequence: list[str]
    reveal_ms: int
    answer_timeout_ms: int


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
    steward_count: int = 1


class SaboteurStartOut(BaseModel):
    session_id: int
    line_size: int
    steward_count: int
    level: int


class SaboteurRevealRequest(BaseModel):
    cell_index: int


class SaboteurRevealOut(BaseModel):
    is_steward: bool
    session_id: int
    score: int
    level: int
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


# --- Football Hangman ---

class HangmanStartOut(BaseModel):
    session_id: int
    category: str
    masked_word: list[str]
    max_wrong: int


class HangmanGuessRequest(BaseModel):
    letter: str


class HangmanGuessOut(BaseModel):
    session_id: int
    masked_word: list[str]
    guessed_letters: list[str]
    wrong_letters: list[str]
    max_wrong: int
    status: str
    is_correct: bool
    word: Optional[str] = None


class HangmanClaimOut(BaseModel):
    reward_coins: int
    new_balance: int


class GameLimitsOut(BaseModel):
    hourly_limit: int
    memory: int
    arena: int
    saboteur: int
    penalty: int
    free_kick: int
    hangman: int
    tactico: int
    pairs: int


# --- Найди пару (card pairs memory match) ---

class PairsStartOut(BaseModel):
    session_id: int
    board_size: int
    total_pairs: int


class PairsFlipRequest(BaseModel):
    position: int = Field(ge=0)


class PairsCardOut(BaseModel):
    position: int
    is_bonus: bool
    player: Optional[PlayerOut] = None


class PairsFlipOut(BaseModel):
    session_id: int
    revealed: list[PairsCardOut]
    # None while waiting for the second flip of an attempt; True/False once
    # a pair attempt resolves (also True for the instant-resolving bonus tile).
    matched: Optional[bool] = None
    matched_pairs: int
    wrong_attempts: int
    total_pairs: int
    status: str


class PairsClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
