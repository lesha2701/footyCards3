from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import ClubBudgetTransactionType, ClubLogoShape, ClubRole, ClubType, TournamentStatus


class AdminClubSummaryOut(BaseModel):
    id: int
    name: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    captain_id: int
    member_count: int
    budget: int
    cups_count: int
    stars_count: int
    founded_at: datetime
    is_disbanded: bool


class AdminClubDetailOut(AdminClubSummaryOut):
    description: str
    invite_code: str
    last_tournament_applied_at: Optional[datetime] = None


class AdminClubMemberOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    role: ClubRole
    joined_at: datetime


class AdminClubBudgetTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    balance_before: int
    balance_after: int
    type: ClubBudgetTransactionType
    description: str
    created_at: datetime


class AdminClubTournamentOut(BaseModel):
    tournament_id: int
    status: TournamentStatus
    rounds_simulated: int
    points: int
    goals_for: int
    goals_against: int
    final_rank: Optional[int] = None
    budget_awarded: Optional[int] = None
    stars_delta: Optional[int] = None
    cup_awarded: Optional[bool] = None
