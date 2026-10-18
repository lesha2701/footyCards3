from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import ClubLogoShape
from app.schemas.club_emblem import ClubEmblemOut


class ClubLeagueRowOut(BaseModel):
    rank: int
    club_id: int
    name: str
    logo_shape: ClubLogoShape
    logo_color: str
    emblem: Optional[ClubEmblemOut] = None
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


class ClubSeasonRowOut(BaseModel):
    rank: int
    club_id: int
    name: str
    logo_shape: ClubLogoShape
    logo_color: str
    emblem: Optional[ClubEmblemOut] = None
    points: int
    # "up" / "down" when the place is in the promotion / relegation zone now.
    zone: Optional[str] = None


class ClubSeasonOut(BaseModel):
    weeks: int
    week_of_season: int
    ends_at: datetime
    promote_count: int
    relegate_count: int
    standings: list[ClubSeasonRowOut]
    my_row: Optional[ClubSeasonRowOut] = None


class ClubLeagueOut(BaseModel):
    enabled: bool
    # The division shown (the player's club's, Бронза outside a club).
    division: int = 0
    division_names: list[str] = []
    division_reward_pct: int = 100
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
    season: Optional[ClubSeasonOut] = None


class ClubLeagueSettleResult(BaseModel):
    clubs_rewarded: int
