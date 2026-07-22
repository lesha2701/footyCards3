from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MemoryStartOut(BaseModel):
    session_id: int
    round_number: int
    sequence: list[str]
    reveal_ms: int


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
