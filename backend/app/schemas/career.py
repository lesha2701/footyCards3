from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.card import UserCardOut
from app.schemas.chemistry import ChemistryOut
from app.schemas.user import UserPublicOut


class CareerCreateIn(BaseModel):
    # Ignored since divisions (the division sets the difficulty); kept so
    # older clients still work.
    difficulty: Optional[str] = None
    # An accepted friend to play the season together with (optional).
    friend_id: Optional[int] = None


class CareerInviteResponseIn(BaseModel):
    accept: bool


class CareerLineupIn(BaseModel):
    slots: dict[str, int] = Field(default_factory=dict)
    formation: str = "4-3-3"
    mentality: str = "BALANCED"
    playstyle: str = "CENTRAL_PLAY"
    # The round the client is preparing for: refused once that round has
    # started (the change would otherwise silently apply to the next one).
    round_index: Optional[int] = None
    # Tactical axes (career_tactics_service.AXES); overrides playstyle.
    tactic: Optional[dict[str, str]] = None


class CareerTacticPreviewIn(BaseModel):
    tactic: dict[str, str]


class CareerAmbitionIn(BaseModel):
    ambition: str


class CareerSquadIn(BaseModel):
    card_ids: list[int]


class CareerCampIn(BaseModel):
    camp: Optional[str] = None


class CareerCupIn(BaseModel):
    rotation: bool


class CareerTrainingIn(BaseModel):
    training: Optional[str] = None
    round_index: Optional[int] = None


class CareerRolesIn(BaseModel):
    roles: dict[str, Optional[str]] = Field(default_factory=dict)
    round_index: Optional[int] = None


class CareerMarkingIn(BaseModel):
    # One of my outfield players to man-mark the next opponent's star; None clears.
    marker_card_id: Optional[int] = None
    round_index: Optional[int] = None


class CareerHalftimeIn(BaseModel):
    """Live match centre, during the break: mentality / some axes for the
    second half and substitutions [{out, in}] (card ids)."""
    mentality: Optional[str] = None
    tactic: Optional[dict[str, str]] = None
    subs: list[dict] = Field(default_factory=list)


class CareerPlanIn(BaseModel):
    """Conditional instructions + substitutions; validated server-side
    (career_tactics_service.clean_plan)."""
    rules: list[dict] = Field(default_factory=list)
    subs: list[dict] = Field(default_factory=list)
    round_index: Optional[int] = None
    # Set-piece takers / schemes (unchanged when omitted).
    set_pieces: Optional[dict] = None


class CareerPlanRuleOut(BaseModel):
    score: str
    margin: int = 0
    from_minute: int
    mentality: Optional[str] = None
    tactic: dict[str, str] = {}


class CareerPlanSubOut(BaseModel):
    minute: int
    slot: Optional[str] = None
    card_id: Optional[int] = None
    min_fatigue: int = 0


class CareerPlanOut(BaseModel):
    rules: list[CareerPlanRuleOut] = []
    subs: list[CareerPlanSubOut] = []


class CareerFamiliarityOut(BaseModel):
    # % rating bonus: accumulated (for the last played tactic), what the
    # currently saved formation + style would get, and the cap.
    stored_pct: float
    current_pct: float
    max_pct: float
    step_pct: float
    keep_pct: int
    axis_keep_pct: int = 100
    last_formation: Optional[str] = None
    last_tactic: Optional[dict[str, str]] = None


class CareerScoutingOut(BaseModel):
    round_index: int
    opponent_index: int
    opponent_name: str
    is_bot: bool
    strength: Optional[int] = None
    formation: Optional[str] = None
    mentality: Optional[str] = None
    # Head-to-head with this bot club over past seasons (living league).
    head_to_head: Optional[dict] = None
    # Their tactic (axes) and its preset code / CUSTOM; None for seasons from
    # before the tactics update (playstyle only) or a friend not yet seen.
    tactic: Optional[dict[str, str]] = None
    preset: Optional[str] = None
    playstyle: Optional[str] = None
    # "last_match" (what they actually played last) or "season_start".
    source: str
    form: list[str] = []
    # My saved tactic vs theirs (career_tactics_service.matchup_report).
    matchup: Optional[dict] = None
    win_pct: Optional[float] = None
    # Pro/legend bots may answer my LAST PLAYED tactic: what they'd pick.
    adaptive: bool = False
    my_last_tactic: Optional[dict[str, str]] = None
    threat: Optional[dict] = None
    # Their best outfield player (bots), my marking of him for this round,
    # and whether a «Легенда» bot will man-mark my own best player.
    star: Optional[dict] = None
    marking: Optional[dict] = None
    marks_you: bool = False


class CareerDifficultyOut(BaseModel):
    code: str
    label: str
    reward_pct: int


class CareerDivisionOut(BaseModel):
    division: int
    name: str
    count: int
    reward_pct: int
    bot_level: str
    bot_level_label: str
    promote: int
    relegate: int


class CareerTeamOut(BaseModel):
    index: int
    name: str
    is_bot: bool
    user_id: Optional[int] = None
    strength: Optional[int] = None


class CareerTableRowOut(BaseModel):
    team_index: int
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    points: int


class CareerMatchOut(BaseModel):
    home: int
    away: int
    hs: Optional[int] = None
    # "as" is a Python keyword: exposed under that name in JSON via the alias.
    away_score: Optional[int] = Field(default=None, alias="as", serialization_alias="as")
    has_events: bool = False

    model_config = {"populate_by_name": True}


class CareerRoundReportOut(BaseModel):
    yellow: list[str] = []
    red: list[str] = []
    suspended: list[str] = []
    injured: list[str] = []
    form_up: list[str] = []
    form_down: list[str] = []
    # Coins for the match (result + home matchday) and my place after the
    # round; absent in rounds played before they were recorded.
    coins: Optional[int] = None
    place: Optional[int] = None


class CareerRoundOut(BaseModel):
    index: int
    at: Optional[datetime] = None
    matches: list[CareerMatchOut]
    report: Optional[CareerRoundReportOut] = None


class CareerParticipantOut(BaseModel):
    user_id: int
    name: str
    status: str
    team_index: int


class CareerMyPlayerOut(BaseModel):
    name: str
    position: str
    rating: int
    club: str = ""
    country: str = ""


class CareerSquadCardOut(BaseModel):
    card: Optional[UserCardOut] = None
    # «Мой игрок» (card is None for this entry).
    my_player: Optional[CareerMyPlayerOut] = None
    card_id: int
    fatigue: int
    injured_rounds: int
    suspended_rounds: int = 0
    yellows: int = 0
    form: int = 0
    owned: bool


class CareerSlotOut(BaseModel):
    code: str
    category: str
    ideal_position: str


class CareerSeasonOut(BaseModel):
    id: int
    status: str
    difficulty: str
    difficulty_label: str
    division: Optional[CareerDivisionOut] = None
    # Set once the season is finished (or left): where the next one is played.
    next_division: Optional[CareerDivisionOut] = None
    rounds_played: int
    total_rounds: int
    schedule: list[datetime]
    next_round_at: Optional[datetime] = None
    invite_expires_at: Optional[datetime] = None
    is_creator: bool
    my_status: str
    my_team_index: int
    final_place: Optional[int] = None
    coins_earned: int
    participants: list[CareerParticipantOut]
    teams: list[CareerTeamOut]
    table: list[CareerTableRowOut]
    rounds: list[CareerRoundOut]
    squad: list[CareerSquadCardOut]
    lineup: dict[str, int]
    slots: list[CareerSlotOut]
    formation: str
    mentality: str
    playstyle: str
    tactics_version: int = 0
    tactic: Optional[dict[str, str]] = None
    squad_size: int = 0
    # Chemistry of the XI for the next round (season's frozen rules).
    chemistry: Optional[ChemistryOut] = None
    set_pieces: Optional[dict] = None
    # Holes / thin lines for the next round (career_service._squad_warnings).
    squad_warnings: list[dict] = []
    # Player roles per line, live match centre (first half + break), and
    # what the coach could still add to the match plan.
    roles: dict[str, str] = {}
    live: Optional[dict] = None
    # My match whose second half is on air right now (watch it live).
    second_half: Optional[dict] = None
    plan_hints: list[dict] = []
    ambition: Optional[str] = None
    ambitions: list[dict] = []
    training: Optional[str] = None
    trainings: list[dict] = []
    # Cup bracket, my status, rotation and prizes (tactics seasons).
    cup: Optional[dict] = None
    # Off-season panel until round 1 of a season that follows another;
    # summary of a finished season.
    offseason: Optional[dict] = None
    summary: Optional[dict] = None
    scouting: Optional[CareerScoutingOut] = None
    familiarity: Optional[CareerFamiliarityOut] = None
    match_plan: Optional[CareerPlanOut] = None
    plan_limits: dict[str, int] = {}


class CareerInviteOut(BaseModel):
    season_id: int
    difficulty_label: str
    from_name: str
    expires_at: Optional[datetime] = None


class CareerViewOut(BaseModel):
    enabled: bool
    difficulties: list[CareerDifficultyOut]
    place_rewards: list[int]
    slots: list[str]
    slot_times: list[datetime] = []
    division: Optional[CareerDivisionOut] = None
    divisions: list[CareerDivisionOut] = []
    tactics_catalog: Optional[dict] = None
    # Long-term coach career: division, reputation and its level, counters.
    profile: Optional[dict] = None
    season: Optional[CareerSeasonOut] = None
    invite: Optional[CareerInviteOut] = None


class CareerMatchEventsOut(BaseModel):
    home_name: str
    away_name: str
    home_score: int
    away_score: int
    events: list[dict]
    # Viewer's own tactical analysis (tactics_version >= 1 seasons only) and
    # which engine side ("a" = home, "b" = away) the viewer was.
    analysis: Optional[dict] = None
    my_side: Optional[str] = None
    # Cup ties level after 90': penalty shootout score and kicks.
    pens: Optional[list[int]] = None
    kicks: Optional[list[dict]] = None


class CareerReplayOut(BaseModel):
    """2D replay of a career match (career_replay_service.build_replay):
    key frames for the compressed show plus the events they illustrate.
    live = only the first half exists yet (the break is running)."""
    home_name: str
    away_name: str
    home_score: int
    away_score: int
    events: list[dict]
    my_side: Optional[str] = None
    live: bool = False
    second_half_at: Optional[str] = None
    replay: dict


# --- friends ---------------------------------------------------------------------

class FriendOut(BaseModel):
    user: UserPublicOut
    since: datetime


class FriendRequestOut(BaseModel):
    request_id: int
    user: UserPublicOut
    created_at: datetime


class FriendsOut(BaseModel):
    friends: list[FriendOut]
    incoming: list[FriendRequestOut]
    outgoing: list[FriendRequestOut]


class FriendRequestIn(BaseModel):
    user_id: int


class FriendRequestResultOut(BaseModel):
    status: str


class FriendRelationOut(BaseModel):
    relation: str


class FriendFeedItemOut(BaseModel):
    kind: str
    user: UserPublicOut
    text: str
    at: datetime
