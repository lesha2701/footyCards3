from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import ClubLogoShape


class ClubLeagueRowOut(BaseModel):
    rank: int
    club_id: int
    name: str
    logo_shape: ClubLogoShape
    logo_color: str
    points: int
    # Budget reward for this place (projected for the current week, paid for a past one).
    reward: int


class ClubLeagueMemberOut(BaseModel):
    user_id: int
    name: str
    games: int
    packs: int
    tasks: int
    # After the weekly per-member cap.
    points: int


class ClubLeagueLastWeekOut(BaseModel):
    week_start: date
    podium: list[ClubLeagueRowOut]
    my_row: Optional[ClubLeagueRowOut] = None


class ClubLeagueOut(BaseModel):
    enabled: bool
    week_start: date
    ends_at: datetime
    points_game: int
    points_pack: int
    points_task: int
    member_weekly_cap: int
    rewards: list[int]
    clubs_count: int
    # Top of the table, plus the player's club appended when it is lower.
    table: list[ClubLeagueRowOut]
    my_row: Optional[ClubLeagueRowOut] = None
    members: list[ClubLeagueMemberOut]
    last_week: Optional[ClubLeagueLastWeekOut] = None


class ClubLeagueSettleResult(BaseModel):
    clubs_rewarded: int
