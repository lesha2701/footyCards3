from typing import Optional

from pydantic import BaseModel


class ClubPenaltyStartRequest(BaseModel):
    club_card_id: int


class ClubPenaltyStartOut(BaseModel):
    session_id: int
    player_rating: int
    first_kicker: str


class ClubPenaltyKickRequest(BaseModel):
    direction: str


class ClubPenaltyKickOut(BaseModel):
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


class ClubPenaltyClaimOut(BaseModel):
    reward_coins: int
    new_club_budget: int
    result: str
    # True when reward_coins is 0 specifically because the player already used up
    # today's rewarded attempts for this game — same meaning as
    # ClubMissingItemClaimOut.daily_cap_reached.
    daily_cap_reached: bool = False


class ClubPenaltyForfeitOut(BaseModel):
    session_id: int
    player_score: int
    bot_score: int
    result: str
