from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import Rarity


class ClubPositionMatchCardOut(BaseModel):
    """Deliberately narrower than PlayerOut — omits `position`, the answer
    the player has to guess. Including it here would let anyone read the
    correct match straight out of the network response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rating: int
    rarity: Rarity
    image_path: Optional[str]


class ClubPositionMatchStartOut(BaseModel):
    session_id: int
    cards: list[ClubPositionMatchCardOut]
    positions: list[str]
    max_mistakes: int


class ClubPositionMatchAttemptRequest(BaseModel):
    player_id: int
    position: str


class ClubPositionMatchAttemptOut(BaseModel):
    session_id: int
    correct: bool
    matched_player_ids: list[int]
    mistakes: int
    max_mistakes: int
    status: str


class ClubPositionMatchClaimOut(BaseModel):
    reward_coins: int
    new_club_budget: int
    # True when reward_coins is 0 specifically because the player already used up
    # today's rewarded attempts for this game — same meaning as
    # ClubGameClaimOut.daily_cap_reached.
    daily_cap_reached: bool = False
