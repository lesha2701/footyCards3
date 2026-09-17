from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import Position, Rarity
from app.schemas.match import MatchActorOut


class FutDraftConfigOut(BaseModel):
    entry_cost: int
    reward_by_wins: list[int]  # index i = reward for reaching i wins (0-4)


class FutDraftCandidateOut(BaseModel):
    """Unlike the position-match games, showing the card's own stats IS the
    point here — the player has to weigh raw rating against position fit and
    club/country synergy, so nothing is hidden."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rating: int
    rarity: Rarity
    position: Position
    club: str
    country: str
    image_path: Optional[str]


class FutDraftSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    player: Optional[FutDraftCandidateOut] = None


class FutDraftStartOut(BaseModel):
    session_id: int
    formation_options: list[str]
    entry_cost: int
    new_balance: int


class FutDraftFormationRequest(BaseModel):
    formation: str


class FutDraftOpenSlotRequest(BaseModel):
    slot_code: str


class FutDraftPickRequest(BaseModel):
    player_id: int


class FutDraftSwapSlotsRequest(BaseModel):
    slot_code_a: str
    slot_code_b: str


class FutDraftStateOut(BaseModel):
    session_id: int
    formation: str
    phase: str  # "drafting" | "ready"
    slots: list[FutDraftSlotOut]
    pending_slot: Optional[str] = None
    candidates: Optional[list[FutDraftCandidateOut]] = None
    team_strength: int
    last_pick_strength_delta: Optional[int] = None
    chemistry_hints: list[str] = []


class FutDraftMatchEventOut(BaseModel):
    """Mirrors app.schemas.match.MatchEventOut field-for-field — Card Arena
    rounds in FUT Draft now run the exact same moment-generation/resolution
    engine as the real Card Arena (app.services.match_service), just against
    a temporary draft squad instead of a persisted Lineup."""
    minute: int
    event_type: str
    team: str  # "user" | "opponent"
    description: str
    payload: Optional[dict] = None


class FutDraftPendingMomentOut(BaseModel):
    """Mirrors app.schemas.match.MatchPendingMomentOut — the next interactive
    shot moment in a Card Arena round, awaiting an action via
    POST /fut-draft/{session_id}/card-arena/action."""
    seq: int
    team: str
    kind: Literal["attack", "defense", "breakaway"]
    shot_type: str
    description: str
    actions: list[Literal["shoot", "pass", "tackle", "block", "keeper", "strike"]]
    actors: dict[str, MatchActorOut]


class FutDraftCardArenaActionRequest(BaseModel):
    action: Literal["shoot", "pass", "tackle", "block", "keeper", "strike"]


class FutDraftTacticoChoiceRequest(BaseModel):
    choice: str


class FutDraftPenaltyKickRequest(BaseModel):
    direction: str


class FutDraftCoinFlipRequest(BaseModel):
    choice: Literal["heads", "tails"]


class FutDraftRoundOut(BaseModel):
    """Covers all shapes with one schema: a fully-resolved Card Arena round
    (round_in_progress=False, events populated), the two genuinely turn-
    based flavors mid-play (round_in_progress=True) — Тактико (phase/
    total_phases/tactic_choices) and Пенальти (kick_number/picked_player/
    zone_choices) — each driven by its own follow-up endpoint one turn at a
    time until round_in_progress flips to False, and a drawn round's
    tiebreaker (game_type="coin_flip", round_in_progress=True while a call
    is pending) via POST /fut-draft/{session_id}/coin-flip."""
    session_id: int
    game_type: str  # "card_arena" | "tactico" | "penalty" | "coin_flip"
    round_in_progress: bool

    events: list[FutDraftMatchEventOut] = []
    pending_moment: Optional[FutDraftPendingMomentOut] = None
    opponent_name: Optional[str] = None

    phase: Optional[int] = None
    total_phases: Optional[int] = None
    tactic_choices: Optional[list[str]] = None
    last_phase_result: Optional[str] = None

    kick_number: Optional[int] = None
    picked_player: Optional[FutDraftCandidateOut] = None
    zone_choices: Optional[list[str]] = None
    last_kick_result: Optional[str] = None

    # A round that ends in a draw is decided by a coin flip instead of
    # ending the series outright — call heads or tails, guess right and it
    # counts as a win, guess wrong and it's a loss.
    coin_flip_choices: Optional[list[Literal["heads", "tails"]]] = None
    coin_flip_result: Optional[Literal["heads", "tails"]] = None

    user_score: int = 0
    bot_score: int = 0

    round_number: Optional[int] = None
    # This round's final "win" | "loss", only once round_in_progress is
    # False — a draw is never terminal, it's replaced by the coin flip's
    # own win/loss before the round is ever reported as finished.
    result: Optional[str] = None
    wins: int = 0
    is_finished: bool = False  # whole draft series finished
    status: str = "in_progress"


class FutDraftClaimOut(BaseModel):
    reward_coins: int
    new_balance: int
    wins: int
    team_strength: int
    is_new_best: bool
    best_squad_strength: int


class FutDraftLeaderboardEntry(BaseModel):
    user_id: int
    display_name: str
    avatar_url: Optional[str]
    best_squad_strength: int
