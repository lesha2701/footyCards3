from pydantic import BaseModel


class ClubStatsOut(BaseModel):
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int
    win_rate_pct: float
    draw_rate_pct: float
    loss_rate_pct: float
    goals_scored_per_match: float
    goals_conceded_per_match: float
