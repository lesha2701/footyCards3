from typing import Optional

from pydantic import BaseModel


class ClubGameStartOut(BaseModel):
    session_id: int
    round_number: int
    icons: list[str]
    sequence: list[str]
    reveal_ms: int
    answer_timeout_ms: int


class ClubGameSubmitRequest(BaseModel):
    answer: list[str]


class ClubGameSubmitOut(BaseModel):
    correct: bool
    session_id: int
    score: int
    status: str
    next_round: Optional[ClubGameStartOut] = None


class ClubGameClaimOut(BaseModel):
    reward_coins: int
    new_club_budget: int
