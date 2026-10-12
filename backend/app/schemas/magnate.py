from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

MagnateMode = Literal["bot", "public", "private"]
MagnateStatus = Literal["lobby", "in_progress", "finished", "cancelled"]
MagnatePhase = Literal["roll", "buy", "end", "moving", "finished"]
MagnateAction = Literal["roll", "buy", "skip", "build", "end", "pay_bail", "use_card"]


class MagnateGroupOut(BaseModel):
    name: str
    color: str


class MagnateCellOut(BaseModel):
    index: int
    type: str
    name: str
    group: Optional[int] = None
    price: Optional[int] = None
    # base, 1–3 «Трибуны», «Арена» (clubs only)
    rent: Optional[list[int]] = None
    build_cost: Optional[int] = None
    owner_seat: Optional[int] = None
    level: int = 0
    # What landing here costs right now (0 when nobody owns it).
    current_rent: int = 0


class MagnatePlayerOut(BaseModel):
    seat: int
    name: str
    is_bot: bool
    is_me: bool
    # Human that left / timed out too often: a bot plays the seat now.
    left: bool = False
    cash: int = 0
    pos: int = 0
    in_jail: bool = False
    jail_cards: int = 0
    bankrupt: bool = False
    capital: int = 0
    missed: int = 0
    place: Optional[int] = None
    reward_coins: int = 0


class MagnateLogOut(BaseModel):
    n: int
    seat: Optional[int] = None
    text: str
    kind: str


class MagnateRollOut(BaseModel):
    seat: int
    dice: list[int]
    n: int


class MagnateMatchOut(BaseModel):
    id: int
    mode: MagnateMode
    status: MagnateStatus
    # Send back with every action; a stale one is rejected (409) instead of
    # being applied to a board the player hasn't seen.
    version: int
    invite_code: Optional[str] = None
    is_creator: bool = False
    my_seat: Optional[int] = None
    seats_total: int = 4
    players: list[MagnatePlayerOut]
    groups: list[MagnateGroupOut]
    cells: list[MagnateCellOut]
    turn: Optional[int] = None
    phase: Optional[MagnatePhase] = None
    my_turn: bool = False
    pending_cell: Optional[int] = None
    build_options: list[int] = []
    can_pay_bail: bool = False
    can_use_card: bool = False
    jail_fine: int = 0
    round: int = 0
    max_rounds: int = 0
    turn_seconds: int = 0
    deadline: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    lobby_deadline: Optional[datetime] = None
    server_now: datetime
    last_roll: Optional[MagnateRollOut] = None
    log: list[MagnateLogOut] = []
    finish_reason: Optional[str] = None
    my_place: Optional[int] = None
    my_reward: int = 0
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class MagnateMatchBriefOut(BaseModel):
    id: int
    mode: MagnateMode
    status: MagnateStatus
    players: int
    my_place: Optional[int] = None
    reward_coins: int = 0
    left: bool = False
    created_at: datetime
    finished_at: Optional[datetime] = None


class MagnateInfoOut(BaseModel):
    start_money: int
    pass_start_bonus: int
    jail_fine: int
    fine_amount: int
    max_rounds: int
    time_limit_minutes: int
    turn_seconds: int
    max_missed_turns: int
    lobby_wait_seconds: int
    room_wait_minutes: int
    place_rewards: list[int]
    bot_reward_pct: int
    daily_limit: int
    rewarded_today: int
    wins: int
    active_match_id: Optional[int] = None


class MagnateRoomPreviewOut(BaseModel):
    id: int
    invite_code: str
    creator_name: str
    status: MagnateStatus
    players: list[str]
    seats_total: int = 4
    is_member: bool = False


class MagnateActionRequest(BaseModel):
    action: MagnateAction
    cell: Optional[int] = None
    version: Optional[int] = None


class MagnateSweepResult(BaseModel):
    advanced: int
