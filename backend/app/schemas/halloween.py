from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.badge import BadgeOut
from app.schemas.card import UserCardOut


class HalloweenShopItemOut(BaseModel):
    code: str
    kind: str  # pack / coins / skill_tokens / badge
    title: str
    price: int
    amount: int = 0
    limit: int = 0  # 0 = unlimited
    bought: int = 0
    available: bool = True
    pack_id: Optional[int] = None
    pack_name: Optional[str] = None
    badge: Optional[BadgeOut] = None


class HalloweenDoorResultOut(BaseModel):
    door: int
    outcome: str  # treat / trick
    kind: str  # coins / pumpkins / pack / zombie_frame / joke
    amount: int = 0
    title: str
    text: str
    pack_name: Optional[str] = None
    cards: list[UserCardOut] = []
    zombie_player_name: Optional[str] = None
    zombie_until: Optional[datetime] = None


class HalloweenCollectionOut(BaseModel):
    id: int
    name: str
    owned: int
    total: int
    reward_coins: int = 0
    reward_pack_name: Optional[str] = None
    completed: bool = False


class HalloweenStateOut(BaseModel):
    enabled: bool
    active: bool
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    pumpkins: int = 0
    earned_total: int = 0
    pumpkins_per_game: int = 0
    games_pumpkins_today: int = 0
    games_daily_cap: int = 0
    pumpkins_per_task: int = 0
    pumpkins_per_daily_chest: int = 0
    pumpkins_per_weekly_chest: int = 0
    boss_multiplier: int = 1
    boss_name: Optional[str] = None
    shop: list[HalloweenShopItemOut] = []
    door_today: Optional[HalloweenDoorResultOut] = None
    door_resets_at: Optional[datetime] = None
    zombie_player_id: Optional[int] = None
    zombie_until: Optional[datetime] = None
    pack_id: Optional[int] = None
    collection: Optional[HalloweenCollectionOut] = None


class HalloweenBuyRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)


class HalloweenBuyOut(BaseModel):
    item_code: str
    pumpkins: int
    new_balance: int
    coins: int = 0
    pack_name: Optional[str] = None
    cards: list[UserCardOut] = []
    skill_code: Optional[str] = None
    skill_tokens: int = 0
    badge: Optional[BadgeOut] = None


class HalloweenAdminOut(BaseModel):
    enabled: bool
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    settings: dict[str, Any]
    defaults: dict[str, Any]
    stats: dict[str, int] = {}


class HalloweenAdminIn(BaseModel):
    enabled: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    settings: Optional[dict[str, Any]] = None
