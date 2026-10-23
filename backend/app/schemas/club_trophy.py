from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import ClubLogoShape
from app.schemas.club_emblem import ClubEmblemOut


class ClubSeasonTrophyOut(BaseModel):
    season_end_week: date
    division: int
    division_name: str
    rank: int
    points: int
    # +1 promoted, -1 relegated, 0 stayed.
    moved: int


class ClubPodiumOut(BaseModel):
    week_start: date
    division: int
    division_name: str
    rank: int
    points: int


class ClubTournamentTrophyOut(BaseModel):
    tournament_id: int
    final_rank: int
    cup: bool
    played_at: datetime


class ClubTrophiesOut(BaseModel):
    club_id: int
    name: str
    logo_shape: ClubLogoShape
    logo_color: str
    emblem: Optional[ClubEmblemOut] = None
    division: int
    division_name: str
    cups_count: int
    stars_count: int
    founded_at: datetime
    seasons: list[ClubSeasonTrophyOut]
    league_gold: int
    league_silver: int
    league_bronze: int
    recent_podiums: list[ClubPodiumOut]
    tournaments_played: int
    tournaments_won: int
    best_tournament_rank: Optional[int] = None
    recent_tournaments: list[ClubTournamentTrophyOut]
    quests_completed: int
    wars_played: int = 0
    wars_won: int = 0
