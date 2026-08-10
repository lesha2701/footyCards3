from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.enums import MatchResult, PenaltyMatchStatus


class PenaltyRoundOut(BaseModel):
    kicker: Literal["user", "opponent"]
    shot_zone: str
    dive_zone: str
    outcome: Literal["goal", "saved", "miss"]


class PenaltyMatchOut(BaseModel):
    id: int
    opponent_name: str
    opponent_user_id: Optional[int] = None
    status: PenaltyMatchStatus
    viewer_side: Literal["user", "opponent"]
    user_score: int
    opponent_score: int
    rounds: list[PenaltyRoundOut]
    kicker: Optional[Literal["user", "opponent"]] = None
    is_viewer_turn: bool = False
    kick_deadline: Optional[datetime] = None
    match_deadline: Optional[datetime] = None
    result: Optional[MatchResult] = None
    rating_delta: int
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class PenaltyChallengeRequest(BaseModel):
    opponent_user_id: int
    user_card_id: int


class PenaltyAcceptRequest(BaseModel):
    user_card_id: int


class PenaltyPickRequest(BaseModel):
    zone: str
