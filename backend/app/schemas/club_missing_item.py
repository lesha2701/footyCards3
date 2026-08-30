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
    # True when reward_coins is 0 (or lower than the earned score) specifically because the
    # player already used up today's rewarded attempts for this game — lets the client explain
    # the zero instead of it looking like a silent bug. False for every other reason (genuinely
    # scored 0, banned from rewards, club disbanded mid-claim).
    daily_cap_reached: bool = False
