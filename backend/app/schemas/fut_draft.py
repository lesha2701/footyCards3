from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import Rarity


class FutDraftConfigOut(BaseModel):
    entry_cost: int


class FutDraftCandidateOut(BaseModel):
    """Unlike the position-match games, showing the card's own stats IS the
    point here — the player has to weigh raw rating against club/country fit,
    so nothing is hidden."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rating: int
    rarity: Rarity
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


class FutDraftStateOut(BaseModel):
    session_id: int
    formation: str
    phase: str  # "drafting" | "ready"
    slots: list[FutDraftSlotOut]
    pending_slot: Optional[str] = None
    candidates: Optional[list[FutDraftCandidateOut]] = None
    team_strength: int
    last_pick_strength_delta: Optional[int] = None


class FutDraftMatchEventOut(BaseModel):
    minute: int
    team: str  # "user" | "bot"
    type: str  # "goal" | "miss"
    text: str


class FutDraftMatchResultOut(BaseModel):
    session_id: int
    round_number: int
    user_score: int
    bot_score: int
    result: str  # "win" | "draw" | "loss"
    events: list[FutDraftMatchEventOut]
    wins: int
    is_finished: bool
    status: str


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
