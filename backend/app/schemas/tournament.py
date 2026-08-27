from typing import Optional

from pydantic import BaseModel


class TournamentApplyResult(BaseModel):
    queued: bool
    tournament_id: Optional[int] = None
    queue_position: Optional[int] = None


class SimulateRoundResult(BaseModel):
    matches_simulated: int


class TournamentStandingOut(BaseModel):
    club_id: int
    club_name: str
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None


class TournamentMatchSummaryOut(BaseModel):
    id: int
    round_number: int
    club_a_id: int
    club_b_id: int
    score_a: int
    score_b: int


class TournamentCurrentOut(BaseModel):
    status: str  # "not_queued" | "queued" | "active" | "completed"
    queue_position: Optional[int] = None
    tournament_id: Optional[int] = None


class TournamentDetailOut(BaseModel):
    id: int
    status: str
    rounds_simulated: int
    standings: list[TournamentStandingOut]
    matches: list[TournamentMatchSummaryOut]


class TournamentMatchDetailOut(BaseModel):
    id: int
    round_number: int
    club_a_id: int
    club_b_id: int
    score_a: int
    score_b: int
    event_log: list[dict]
