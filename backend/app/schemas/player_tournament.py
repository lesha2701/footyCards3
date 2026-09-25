from typing import Optional

from pydantic import BaseModel


class PlayerTournamentApplyResult(BaseModel):
    queued: bool
    tournament_id: Optional[int] = None
    queue_position: Optional[int] = None
    queue_size: int = 16


class PlayerTournamentCurrentOut(BaseModel):
    status: str  # "not_queued" | "queued" | "active" | "completed"
    queue_position: Optional[int] = None
    queue_size: int = 16
    tournament_id: Optional[int] = None
    can_apply: bool = False


class PlayerTournamentReminderResult(BaseModel):
    users_notified: int


class PlayerTournamentStandingOut(BaseModel):
    user_id: int
    display_name: str
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None
    coins_awarded: Optional[int] = None
    rating_delta: Optional[int] = None


class PlayerTournamentMatchSummaryOut(BaseModel):
    id: int
    round_number: int
    user_a_id: int
    user_b_id: int
    score_a: int
    score_b: int


class PlayerTournamentDetailOut(BaseModel):
    id: int
    status: str
    rounds_simulated: int
    standings: list[PlayerTournamentStandingOut]
    matches: list[PlayerTournamentMatchSummaryOut]
    next_round_seconds_remaining: Optional[int] = None


class PlayerTournamentMatchDetailOut(BaseModel):
    id: int
    round_number: int
    user_a_id: int
    user_b_id: int
    user_a_name: str
    user_b_name: str
    score_a: int
    score_b: int
    event_log: list[dict]


class TournamentRatingRowOut(BaseModel):
    user_id: int
    display_name: str
    tournament_rating: int
