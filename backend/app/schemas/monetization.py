from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.badge import BadgeOut
from app.schemas.card import UserCardOut

CosmeticKind = Literal["profile_frame", "profile_background", "card_skin"]
RarityName = Literal["common", "rare", "epic", "legendary", "diamond"]


# --- cosmetics ------------------------------------------------------------------------


class CosmeticOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: CosmeticKind
    name: str
    description: Optional[str] = None
    style_key: str
    coins_price: int
    stars_price: int
    is_exclusive: bool
    is_active: bool
    sort_order: int


class CosmeticIn(BaseModel):
    kind: CosmeticKind
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    style_key: str = Field(min_length=1, max_length=32)
    coins_price: int = Field(default=0, ge=0)
    stars_price: int = Field(default=0, ge=0, le=10000)
    is_exclusive: bool = False
    is_active: bool = True
    sort_order: int = 0


class CosmeticCatalogItemOut(CosmeticOut):
    owned: bool
    equipped: bool


class EquippedCosmeticsOut(BaseModel):
    """Style keys of what the player has on (null = default look)."""

    frame: Optional[str] = None
    background: Optional[str] = None
    card_skin: Optional[str] = None


class CosmeticCatalogOut(BaseModel):
    items: list[CosmeticCatalogItemOut]
    equipped: EquippedCosmeticsOut
    balance: int


class CosmeticEquipIn(BaseModel):
    kind: CosmeticKind
    cosmetic_id: Optional[int] = None  # null = take off


# --- reward bundles -------------------------------------------------------------------


class RewardBundleIn(BaseModel):
    coins: int = Field(default=0, ge=0)
    pack_id: Optional[int] = None
    card_rarity: Optional[RarityName] = None
    badge_id: Optional[int] = None
    cosmetic_id: Optional[int] = None


class RewardBundleOut(BaseModel):
    """What a reward slot contains — shown before claiming/paying."""

    coins: int = 0
    pack_id: Optional[int] = None
    pack_name: Optional[str] = None
    card_rarity: Optional[RarityName] = None
    badge: Optional[BadgeOut] = None
    cosmetic: Optional[CosmeticOut] = None

    @property
    def is_empty(self) -> bool:
        return not (self.coins or self.pack_id or self.card_rarity or self.badge or self.cosmetic)


class GrantedRewardsOut(BaseModel):
    coins: int = 0
    pack_name: Optional[str] = None
    cards: list[UserCardOut] = []
    badge: Optional[BadgeOut] = None
    cosmetic: Optional[CosmeticOut] = None
    new_balance: int = 0


# --- monthly login calendar -----------------------------------------------------------


class CalendarDayOut(BaseModel):
    day: int
    date: date
    reward: RewardBundleOut
    status: Literal["claimed", "today", "missed", "future"]
    claim_method: Optional[str] = None
    is_big: bool = False


class CalendarOut(BaseModel):
    month: date  # first day of the month
    today: date
    days: list[CalendarDayOut]
    claimed_count: int
    days_in_month: int
    already_claimed_today: bool
    month_bonus: RewardBundleOut
    month_bonus_claimed: bool
    catchup_coins: int
    catchup_stars: int
    catchups_left: int


class CalendarClaimOut(BaseModel):
    day: int
    granted: GrantedRewardsOut
    month_bonus: Optional[GrantedRewardsOut] = None
    new_balance: int


class CalendarCatchupIn(BaseModel):
    date: date


class CalendarDayIn(RewardBundleIn):
    day: int = Field(ge=0, le=31)


class CalendarTemplateIn(BaseModel):
    days: list[CalendarDayIn]


class CalendarTemplateDayOut(RewardBundleIn):
    day: int


# --- «Клубный абонемент» --------------------------------------------------------------


class ClubPassPerksOut(BaseModel):
    daily_coins: int
    daily_pack: Optional[RewardBundleOut] = None
    extra_rewarded_attempts: int
    frame: Optional[CosmeticOut] = None
    badge: Optional[BadgeOut] = None
    ad_free: bool


class ClubPassOut(BaseModel):
    enabled: bool
    stars_price: int
    perks: ClubPassPerksOut
    is_active: bool
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    daily_claimed_today: bool = False


# --- «Сезонный пропуск» --------------------------------------------------------------


class SeasonLevelOut(BaseModel):
    level: int
    xp_required: int
    free: RewardBundleOut
    premium: RewardBundleOut
    reached: bool
    free_claimed: bool
    premium_claimed: bool


class SeasonPassOut(BaseModel):
    enabled: bool
    season_id: Optional[int] = None
    name: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    premium_stars: int = 0
    xp: int = 0
    level: int = 0
    next_level_xp: Optional[int] = None
    is_premium: bool = False
    levels: list[SeasonLevelOut] = []
    claimable: int = 0
    locked_premium: int = 0
    xp_per_game: int = 0
    xp_per_daily_claim: int = 0


class SeasonClaimIn(BaseModel):
    level: int
    track: Literal["free", "premium"]


class SeasonLevelIn(BaseModel):
    level: int = Field(ge=1, le=200)
    xp_required: int = Field(ge=0)
    free: RewardBundleIn = RewardBundleIn()
    premium: RewardBundleIn = RewardBundleIn()


class SeasonIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    starts_at: datetime
    ends_at: datetime
    premium_stars: int = Field(default=399, ge=1, le=10000)
    is_active: bool = True
    levels: list[SeasonLevelIn] = []


class SeasonAdminOut(BaseModel):
    id: int
    name: str
    starts_at: datetime
    ends_at: datetime
    premium_stars: int
    is_active: bool
    levels: list[SeasonLevelIn]
    players: int = 0
    premium_players: int = 0


# --- starter offer --------------------------------------------------------------------


class StarterOfferOut(BaseModel):
    available: bool
    stars_price: int = 0
    contents: RewardBundleOut = RewardBundleOut()
    expires_at: Optional[datetime] = None
    seen: bool = False
    purchased: bool = False


# --- Stars purchases of these products -------------------------------------------------


class ShopInvoiceStatusOut(BaseModel):
    status: Literal["pending", "completed"]
    product: Optional[str] = None
