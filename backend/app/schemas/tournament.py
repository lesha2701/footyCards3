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
    budget_awarded: Optional[int] = None
    stars_delta: Optional[int] = None
    cup_awarded: Optional[bool] = None


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
    # Whether the club could submit a new application right now (cooldown elapsed, not
    # already in an active tournament, not already queued) — independent of `status`, since
    # `status` can be "completed" (still showing the last finished tournament) while the club
    # is simultaneously free to apply for a new one.
    can_apply: bool = False
    cooldown_seconds_remaining: Optional[int] = None


class TournamentDetailOut(BaseModel):
    id: int
    status: str
    rounds_simulated: int
    standings: list[TournamentStandingOut]
    matches: list[TournamentMatchSummaryOut]
    # None once the tournament is completed (or all 14 rounds are in) — otherwise the
    # seconds until the next scheduled simulation slot fires the next round.
    next_round_seconds_remaining: Optional[int] = None


class TournamentMatchDetailOut(BaseModel):
    id: int
    round_number: int
    club_a_id: int
    club_b_id: int
    score_a: int
    score_b: int
    event_log: list[dict]


class LineupReminderResult(BaseModel):
    clubs_notified: int
