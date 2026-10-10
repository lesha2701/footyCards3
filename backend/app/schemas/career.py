from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.card import UserCardOut
from app.schemas.user import UserPublicOut


class CareerCreateIn(BaseModel):
    difficulty: str = "pro"
    # An accepted friend to play the season together with (optional).
    friend_id: Optional[int] = None


class CareerInviteResponseIn(BaseModel):
    accept: bool


class CareerLineupIn(BaseModel):
    slots: dict[str, int] = Field(default_factory=dict)
    formation: str = "4-3-3"
    mentality: str = "BALANCED"
    playstyle: str = "CENTRAL_PLAY"


class CareerDifficultyOut(BaseModel):
    code: str
    label: str
    reward_pct: int


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


class CareerRoundOut(BaseModel):
    index: int
    at: Optional[datetime] = None
    matches: list[CareerMatchOut]


class CareerParticipantOut(BaseModel):
    user_id: int
    name: str
    status: str
    team_index: int


class CareerSquadCardOut(BaseModel):
    card: Optional[UserCardOut] = None
    card_id: int
    fatigue: int
    injured_rounds: int
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
    season: Optional[CareerSeasonOut] = None
    invite: Optional[CareerInviteOut] = None


class CareerMatchEventsOut(BaseModel):
    home_name: str
    away_name: str
    home_score: int
    away_score: int
    events: list[dict]


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
