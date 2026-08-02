from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchDifficulty, MatchResult, TacticoMatchStatus, TacticoOpponentType
from app.schemas.card import UserCardOut


class TacticoSquadOut(BaseModel):
    is_complete: bool
    cards: list[UserCardOut]
    max_legendary: int
    max_epic: int


class TacticoSquadSetRequest(BaseModel):
    user_card_ids: list[int]


class TacticoCardOut(BaseModel):
    """Denormalized player snapshot shown in a round result — self-contained
    so a finished round's display never depends on the card, or the bot's
    synthetic squad, still existing/being queryable later."""

    user_card_id: Optional[int] = None
    player_id: int
    display_name: str
    position: str
    image_path: Optional[str] = None
    rarity: str
    rating: int
    attack_rating: int
    defense_rating: int


class TacticoRoundOut(BaseModel):
    index: int
    phase: Literal["attack", "defense"]
    user_card: Optional[TacticoCardOut] = None
    opponent_card: Optional[TacticoCardOut] = None
    winner: Optional[Literal["user", "opponent", "draw"]] = None


class TacticoMatchOut(BaseModel):
    id: int
    opponent_type: TacticoOpponentType
    opponent_name: str
    opponent_user_id: Optional[int] = None
    difficulty: Optional[MatchDifficulty] = None
    status: TacticoMatchStatus
    viewer_side: Literal["user", "opponent"]
    user_score: int
    opponent_score: int
    rounds: list[TacticoRoundOut]
    current_phase: Optional[Literal["attack", "defense"]] = None
    pickable_cards: Optional[list[TacticoCardOut]] = None
    waiting_for_opponent: bool = False
    round_deadline: Optional[datetime] = None
    result: Optional[MatchResult] = None
    reward_coins: int
    rating_delta: int
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class TacticoChallengeRequest(BaseModel):
    receiver_id: int


class TacticoBotMatchRequest(BaseModel):
    difficulty: MatchDifficulty = MatchDifficulty.medium


class TacticoRoundSubmitRequest(BaseModel):
    user_card_id: int


class TacticoStatsOut(BaseModel):
    tactics_rating: int
    tactics_rank: Optional[int] = None
