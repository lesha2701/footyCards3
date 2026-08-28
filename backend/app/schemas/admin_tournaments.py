from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TournamentStatus


class AdminTournamentSummaryOut(BaseModel):
    id: int
    status: TournamentStatus
    rounds_simulated: int
    club_count: int
    created_at: datetime


class AdminTournamentStatsOut(BaseModel):
    active_count: int
    completed_count: int
