from datetime import date, datetime
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
    rating_delta: Optional[int] = None


class PenaltyClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
    result: str


class PenaltyForfeitOut(BaseModel):
    session_id: int
    player_score: int
    bot_score: int
    result: str
    rating_delta: int


class PenaltyStatsOut(BaseModel):
    penalty_rating: int
    penalty_rank: Optional[int] = None


# --- Penalty 3D (the bot shootout; PvP stays on the classic endpoints) ---

class Penalty3DKickOut(BaseModel):
    """The next kick of the shootout. «player» shoots: the scene is
    createPenaltySetup(seed, rating) and the bot keeps goal; «bot» shoots:
    penaltyBotShot(seed) against the player's dive."""
    kick_index: int
    kicker: str  # player | bot
    seed: int


class Penalty3DStartOut(BaseModel):
    session_id: int
    rating: int
    kick: Penalty3DKickOut
    # «Мой игрок» gear worn in the 3D scene (cosmetic codes; None = default).
    celebration: str | None = None
    ball: str | None = None
    boots: str | None = None
    gloves: str | None = None


class Penalty3DDive(BaseModel):
    """The player's dive: where (mm on the goal plane) and when (ms from the
    strike; negative = during the run-up)."""
    x: int = Field(ge=-4000, le=4000)
    y: int = Field(ge=0, le=3000)
    reaction_ms: int = Field(ge=-2000, le=3000)


class Penalty3DSaveRequest(BaseModel):
    dive: Optional[Penalty3DDive] = None


class Penalty3DResultOut(BaseModel):
    kicker: str
    outcome: str  # goal | save | miss
    bot_kind: Optional[str] = None
    player_score: int
    bot_score: int
    is_finished: bool
    result: Optional[str] = None
    rating_delta: Optional[int] = None
    next_kick: Optional[Penalty3DKickOut] = None


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


# --- Free Kick 3D (the free kick mode; the classic one above is kept, unlinked) ---

class FreeKick3DKickOut(BaseModel):
    """One position of the series: the client builds the scene from
    `seed` + the series' card rating, exactly as the server will replay it."""
    kick_index: int
    seed: int


class FreeKick3DStartOut(BaseModel):
    session_id: int
    rating: int
    total_kicks: int
    kick: FreeKick3DKickOut
    # Goals in a row so far («Серия без промахов»), carried across series.
    streak: int = 0
    # «Мой игрок» gear worn in the 3D scene (cosmetic codes; None = default).
    celebration: Optional[str] = None
    ball: Optional[str] = None
    boots: Optional[str] = None
    gloves: Optional[str] = None


class FreeKick3DShotRequest(BaseModel):
    """The swipe as the client quantized it (integer thousandths of the
    viewport height, dy < 0 is upwards; whole milliseconds)."""
    dx: int = Field(ge=-1500, le=1500)
    dy: int = Field(ge=-1500, le=-1)
    curve: int = Field(ge=-500, le=500)
    duration_ms: int = Field(ge=40, le=2000)


class FreeKick3DShotOut(BaseModel):
    outcome: str  # goal | save | miss | wall
    bonuses: list[str]  # corner | curl
    coins_this_kick: int
    total_coins: int
    is_finished: bool
    next_kick: Optional[FreeKick3DKickOut] = None
    # Goals in a row after this kick, and the bonus it paid (in coins_this_kick).
    streak: int = 0
    streak_bonus: int = 0


class FreeKickChallengeTarget(BaseModel):
    """A ring on the goal plane (m): centre and radius."""
    x: float
    y: float
    r: float


class FreeKickChallengeStartOut(BaseModel):
    """Today's attempt (new, or picked up mid-way): the positions are
    `seed` + `rating` as in the series; one target per kick."""
    session_id: int
    rating: int
    total_kicks: int
    kick: FreeKick3DKickOut
    targets: list[FreeKickChallengeTarget]
    score: int
    hits: int
    celebration: Optional[str] = None
    ball: Optional[str] = None
    boots: Optional[str] = None
    gloves: Optional[str] = None


class FreeKickChallengeShotOut(BaseModel):
    outcome: str  # goal | save | miss | wall
    hit: bool
    points: int
    score: int
    hits: int
    is_finished: bool
    next_kick: Optional[FreeKick3DKickOut] = None
    # On the last kick: the coins paid, the balance and the day's place.
    reward_coins: int = 0
    new_balance: Optional[int] = None
    rank: Optional[int] = None


class FreeKickChallengeMine(BaseModel):
    score: int
    hits: int
    rank: int
    finished: bool
    reward_coins: int


class FreeKickChallengeRow(BaseModel):
    rank: int
    name: str
    score: int
    hits: int
    finished: bool
    is_me: bool


class FreeKickChallengeOut(BaseModel):
    day: date
    total_kicks: int
    coins_per_hit: int
    perfect_bonus: int
    players: int
    my: Optional[FreeKickChallengeMine] = None
    top: list[FreeKickChallengeRow]


class FreeKick3DRefillOut(BaseModel):
    """Whether the player may buy another series now, and for what: the
    day's first refill costs coins, the following ones Telegram Stars."""
    can_refill: bool
    # The hourly series is used up (a banked one counts as available).
    on_cooldown: bool
    bonus_series: int
    refills_today: int
    daily_limit: int
    price_coins: Optional[int] = None
    price_stars: Optional[int] = None
    retry_after_seconds: int = 0
    new_balance: Optional[int] = None


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
    # The free kick has its own cap of series per hour.
    free_kick_hourly_limit: int
    memory: int
    arena: int
    saboteur: int
    penalty: int
    free_kick: int
    hangman: int
    tactico: int
    pairs: int
    stratego: int
    magnate: int
    mordoboi: int
    kontra: int = 0
    # When a game's hourly cap is used up: the moment it frees up again
    # (key = the field name above). Games with plays left are absent.
    resets_at: dict[str, datetime] = {}


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
