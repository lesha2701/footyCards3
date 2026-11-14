from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.schemas.halloween import HalloweenCollectionOut
from app.schemas.monetization import GrantedRewardsOut, RewardBundleOut


class AnniversaryCalendarDayOut(BaseModel):
    n: int
    status: Literal["claimed", "today", "locked"]
    reward: RewardBundleOut


class AnniversaryTierOut(BaseModel):
    pct: int
    target: int
    reached: bool
    claimed: bool
    reward: RewardBundleOut


class AnniversaryCommunityOut(BaseModel):
    total: int
    goal: int
    my_games: int
    min_games: int
    tiers: list[AnniversaryTierOut]
    claimable: bool = False


class AnniversaryStateOut(BaseModel):
    enabled: bool
    active: bool
    finished: bool = False
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    claim_until: Optional[datetime] = None
    teaser_days: int = 0
    calendar: list[AnniversaryCalendarDayOut] = []
    calendar_claimed: int = 0
    calendar_ready: bool = False
    day_resets_at: Optional[datetime] = None
    community: Optional[AnniversaryCommunityOut] = None
    recap_coins: int = 0
    recap_claimed: bool = False
    collection: Optional[HalloweenCollectionOut] = None
    pack_id: Optional[int] = None


class AnniversaryRecapOut(BaseModel):
    days_with_us: int
    active_days: int
    packs_opened: int
    cards: int
    unique_players: int
    coins_earned: int
    trades: int
    badges: int
    player_number: int
    games: int
    favourite_mode: Optional[str] = None
    favourite_mode_games: int = 0
    best_card_name: Optional[str] = None
    best_card_rating: Optional[int] = None
    best_card_rarity: Optional[str] = None
    best_card_image: Optional[str] = None
    best_card_position: Optional[str] = None
    cards_better_than_pct: int = 0


class AnniversaryClaimOut(BaseModel):
    title: str
    rewards: GrantedRewardsOut
    new_balance: int


class AnniversaryAdminOut(BaseModel):
    enabled: bool
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    settings: dict[str, Any]
    defaults: dict[str, Any]
    stats: dict[str, Any] = {}


class AnniversaryAdminIn(BaseModel):
    enabled: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    settings: Optional[dict[str, Any]] = None
