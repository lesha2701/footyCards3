from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.career import CareerTableRowOut
from app.schemas.my_player import MyPlayerOut


class PlayerCareerContractIn(BaseModel):
    club_key: str


class PlayerCareerClubOut(BaseModel):
    key: str
    name: str
    rating: int
    is_demo: bool
    real_cards: int
    reputation_needed: int
    # None = open for the player.
    locked_reason: Optional[str] = None
    stars: list[str] = []


class PlayerCareerMyRoundOut(BaseModel):
    played: bool
    goals: int
    assists: int
    rating: Optional[float] = None
    own: int
    opp: int
    opponent: str


class PlayerCareerRoundOut(BaseModel):
    index: int
    at: Optional[datetime] = None
    home: Optional[int] = None
    away: Optional[int] = None
    hs: Optional[int] = None
    away_score: Optional[int] = None
    me: Optional[PlayerCareerMyRoundOut] = None


class PlayerCareerTeamOut(BaseModel):
    index: int
    name: str
    rating: int
    is_mine: bool


class PlayerCareerScorerOut(BaseModel):
    name: str
    team: str
    goals: int


class PlayerCareerSeasonStatsOut(BaseModel):
    matches: int
    goals: int
    assists: int
    avg_rating: Optional[float] = None


class PlayerCareerOfferOut(BaseModel):
    key: str
    name: str
    rating: int


class PlayerCareerSeasonOut(BaseModel):
    id: int
    status: str
    rounds_played: int
    total_rounds: int
    next_round_at: Optional[datetime] = None
    teams: list[PlayerCareerTeamOut]
    table: list[CareerTableRowOut]
    rounds: list[PlayerCareerRoundOut]
    stats: PlayerCareerSeasonStatsOut
    scorers: list[PlayerCareerScorerOut]
    final_place: Optional[int] = None
    coins_earned: int
    awards: list[str] = []
    offers: list[PlayerCareerOfferOut] = []


class PlayerCareerTotalsOut(BaseModel):
    seasons: int = 0
    matches: int = 0
    goals: int = 0
    assists: int = 0
    titles: int = 0
    top_scorer: int = 0
    mvp: int = 0


class PlayerCareerRewardsOut(BaseModel):
    win: int
    draw: int
    goal: int
    xp: int
    places: list[int]


class PlayerCareerViewOut(BaseModel):
    enabled: bool
    has_player: bool
    player: Optional[MyPlayerOut] = None
    rating: Optional[int] = None
    reputation: int = 0
    career: Optional[PlayerCareerTotalsOut] = None
    club: Optional[PlayerCareerClubOut] = None
    clubs: list[PlayerCareerClubOut] = []
    season: Optional[PlayerCareerSeasonOut] = None
    can_change_club: bool = True
    rewards: Optional[PlayerCareerRewardsOut] = None
