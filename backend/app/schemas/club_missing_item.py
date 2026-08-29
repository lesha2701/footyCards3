from typing import Optional

from pydantic import BaseModel


class ClubMissingItemStartOut(BaseModel):
    session_id: int
    round_number: int
    items: list[str]


class ClubMissingItemRevealOut(BaseModel):
    session_id: int
    round_number: int
    items_shown: list[str]
    hide_after_ms: int
    answer_timeout_ms: int


class ClubMissingItemSubmitRequest(BaseModel):
    answer: str


class ClubMissingItemSubmitOut(BaseModel):
    correct: bool
    session_id: int
    score: int
    status: str
    next_round: Optional[ClubMissingItemStartOut] = None


class ClubMissingItemClaimOut(BaseModel):
    reward_coins: int
    new_club_budget: int
