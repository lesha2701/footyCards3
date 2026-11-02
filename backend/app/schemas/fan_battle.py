from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.badge import BadgeOut
from app.schemas.card import UserCardOut
from app.schemas.halloween import HalloweenCollectionOut


class FanSideOut(BaseModel):
    code: str
    name: str
    emoji: str
    color: str
    members: int = 0
    points: int = 0
    today_points: int = 0
    # Points of its fans get +N % while the side has noticeably fewer fans.
    underdog_bonus_pct: int = 0


class FanTopOut(BaseModel):
    user_id: int
    name: str
    points: int


class FanDayOut(BaseModel):
    day: date
    finished: bool
    points: dict[str, int]
    # code of the winning side, "draw", or null while the day runs
    winner: Optional[str] = None
    my_points: int = 0
    reward_coins: int = 0  # what the player gets for this day (0 = not eligible)
    claimed: bool = False


class FanMilestoneOut(BaseModel):
    points: int
    kind: str  # coins / skill_tokens / pack / badge
    amount: int = 0
    title: str
    reached: bool = False
    claimed: bool = False
    badge: Optional[BadgeOut] = None
    pack_name: Optional[str] = None


class FanFinalOut(BaseModel):
    winner: Optional[str] = None  # side code or "draw"
    my_rank: Optional[int] = None
    eligible: bool = False
    coins: int = 0
    pack_name: Optional[str] = None
    badge: Optional[BadgeOut] = None
    claimed: bool = False


class FanBattleStateOut(BaseModel):
    enabled: bool
    active: bool
    finished: bool = False
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    claim_until: Optional[datetime] = None
    can_join: bool = False
    teaser_days: int = 0  # the home screen shows the event this many days before the start
    sides: list[FanSideOut] = []
    my_side: Optional[str] = None
    my_points: int = 0
    my_today_points: int = 0
    my_rank: Optional[int] = None
    points_per_game: int = 0
    games_points_today: int = 0
    games_daily_cap: int = 0
    points_per_task: int = 0
    points_per_daily_chest: int = 0
    points_per_weekly_chest: int = 0
    boss_name: Optional[str] = None
    boss_multiplier: int = 1
    daily_min_points: int = 0
    daily_win_coins: int = 0
    daily_lose_coins: int = 0
    day_resets_at: Optional[datetime] = None
    days: list[FanDayOut] = []
    milestones: list[FanMilestoneOut] = []
    final: Optional[FanFinalOut] = None
    final_win_coins: int = 0
    final_lose_coins: int = 0
    final_min_points: int = 0
    top_n: int = 0
    top_bonus_coins: int = 0
    top: dict[str, list[FanTopOut]] = {}
    claimable: int = 0
    collection: Optional[HalloweenCollectionOut] = None


class FanClaimOut(BaseModel):
    claimed: int
    coins: int = 0
    skill_tokens: list[dict[str, Any]] = []
    badges: list[BadgeOut] = []
    pack_names: list[str] = []
    cards: list[UserCardOut] = []
    titles: list[str] = []
    new_balance: int


class FanBattleAdminOut(BaseModel):
    enabled: bool
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    settings: dict[str, Any]
    defaults: dict[str, Any]
    stats: dict[str, Any] = {}


class FanBattleAdminIn(BaseModel):
    enabled: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    settings: Optional[dict[str, Any]] = None
