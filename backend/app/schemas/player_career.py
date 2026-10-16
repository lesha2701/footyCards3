from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.career import CareerTableRowOut
from app.schemas.my_player import MyPlayerOut


class PlayerCareerContractIn(BaseModel):
    club_key: str


class PlayerCareerCounterIn(BaseModel):
    # +10 / +20 / +30 percent salary and bonus.
    raise_pct: int


class PlayerCareerLeagueOut(BaseModel):
    id: int
    name: str
    level: int


class PlayerCareerClubOut(BaseModel):
    key: str
    name: str
    rating: int
    is_demo: bool
    real_cards: int
    reputation_needed: int
    # None = open for the player.
    locked_reason: Optional[str] = None
    # Best real players of the club.
    stars: list[str] = []
    # Market salary per season for this player.
    salary: int = 0
    league: Optional[PlayerCareerLeagueOut] = None
    # Division (1 = top).
    level: int = 1
    # Club prestige, 1-5.
    club_stars: int = 1


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
    club_stars: int = 1
    league: Optional[str] = None
    level: int = 1
    salary: int
    bonus: int
    counters: int = 0
    # open | accepted | closed | withdrawn
    status: str
    # The current club's renewal.
    renewal: bool = False
    # Result of the last counter-offer: agreed | walked.
    last: Optional[str] = None


class PlayerCareerObjectiveOut(BaseModel):
    # place | goals | clean_sheets | avg_rating
    code: str
    target: float
    label: str
    value: float
    # Active season: on track; finished: met.
    met: bool


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
    league: Optional[PlayerCareerLeagueOut] = None
    objectives: list[PlayerCareerObjectiveOut] = []
    salary: int = 0
    objective_coins: int = 0


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
    objective_coins: int = 0
    objective_rep: int = 0


class PlayerCareerHistoryOut(BaseModel):
    id: int
    club: str
    club_rating: Optional[int] = None
    place: Optional[int] = None
    matches: int
    goals: int
    assists: int
    avg_rating: Optional[float] = None
    awards: list[str] = []
    coins_earned: int
    finished_at: Optional[datetime] = None


class PlayerCareerFreshnessOut(BaseModel):
    value: int
    per_match: int


class PlayerCareerContractOut(BaseModel):
    salary: int
    seasons_left: int
    # Ran out (or the club is gone): only lower divisions or offers remain.
    expired: bool
    free_agent_level: int


class PlayerCareerNationalOut(BaseModel):
    country: Optional[str] = None
    prestige_needed: int
    called_up: bool


class PlayerCareerCupMatchOut(BaseModel):
    home: str
    away: str
    home_mine: bool
    away_mine: bool
    hs: Optional[int] = None
    away_score: Optional[int] = None
    pens: Optional[bool] = None
    winner_mine: Optional[bool] = None
    home_won: Optional[bool] = None


class PlayerCareerCupMyRoundOut(BaseModel):
    played: bool
    goals: int
    assists: int
    rating: Optional[float] = None
    own: int
    opp: int
    pens: bool = False
    won: bool
    opponent: str


class PlayerCareerCupRoundOut(BaseModel):
    label: str
    at: Optional[datetime] = None
    matches: list[PlayerCareerCupMatchOut]
    me: Optional[PlayerCareerCupMyRoundOut] = None


class PlayerCareerCupOut(BaseModel):
    id: int
    # cl | national
    kind: str
    title: str
    status: str
    rounds_played: int
    next_round_at: Optional[datetime] = None
    alive: bool
    won: bool
    award: Optional[str] = None
    coins_earned: int
    rounds: list[PlayerCareerCupRoundOut]
    my_team: Optional[str] = None


class PlayerCareerGoldenBallEntryOut(BaseModel):
    place: int
    user_id: int
    user_name: str
    is_me: bool
    matches: int
    goals: int
    assists: int
    clean_sheets: int = 0
    # GK | DEF | MID | FWD
    line: str = "FWD"
    avg_rating: Optional[float] = None
    score: float


class PlayerCareerGoldenBallWinnerOut(BaseModel):
    month: str
    month_label: str
    user_name: str
    is_me: bool
    score: float
    goals: int
    avg_rating: float


class PlayerCareerGoldenBallOut(BaseModel):
    month: str
    month_label: str
    min_matches: int
    prize_coins: int
    prize_prestige: int
    # Points per goal / assist / clean sheet by line.
    weights: dict[str, dict[str, int]] = {}
    table: list[PlayerCareerGoldenBallEntryOut]
    me: Optional[PlayerCareerGoldenBallEntryOut] = None
    winners: list[PlayerCareerGoldenBallWinnerOut]


class PlayerCareerHaggleOut(BaseModel):
    club: str
    agreed: bool
    chance: int


class PlayerCareerViewOut(BaseModel):
    enabled: bool
    has_player: bool
    # Coin balance, to refresh the top bar after a signing bonus.
    balance: Optional[int] = None
    player: Optional[MyPlayerOut] = None
    rating: Optional[int] = None
    reputation: int = 0
    career: Optional[PlayerCareerTotalsOut] = None
    club: Optional[PlayerCareerClubOut] = None
    clubs: list[PlayerCareerClubOut] = []
    season: Optional[PlayerCareerSeasonOut] = None
    can_change_club: bool = True
    rewards: Optional[PlayerCareerRewardsOut] = None
    history: list[PlayerCareerHistoryOut] = []
    freshness: Optional[PlayerCareerFreshnessOut] = None
    contract: Optional[PlayerCareerContractOut] = None
    national: Optional[PlayerCareerNationalOut] = None
    cups: list[PlayerCareerCupOut] = []
    golden_ball: Optional[PlayerCareerGoldenBallOut] = None
    haggle_steps: list[int] = []
    max_counters: int = 2
    # Only on the counter-offer response.
    haggle: Optional[PlayerCareerHaggleOut] = None
