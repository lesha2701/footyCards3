from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.badge import BadgeOut
from app.schemas.monetization import CosmeticOut


class LuckyBoardSideOut(BaseModel):
    coins: int = 0
    tokens: int = 0
    shards: int = 0
    cosmetic: bool = False


class LuckyBoardOutcomeOut(BaseModel):
    code: str
    label: str
    # The symbol shown three times for a triple outcome; None for pair / miss.
    symbol: Optional[str] = None
    # Exact chances in percent, from the same table the server rolls on.
    free_pct: float
    paid_pct: float
    free: LuckyBoardSideOut
    paid: LuckyBoardSideOut


class LuckyBoardStatusOut(BaseModel):
    enabled: bool
    free_per_day: int
    free_remaining: int
    paid_spins: int
    paid_bought_today: int
    paid_daily_limit: int
    stars_cost: int
    hourly_limit: int
    hourly_remaining: int
    hour_resets_at: Optional[datetime] = None
    shards: int
    shards_per_token: int
    next_reset_at: datetime
    symbols: list[str]
    outcomes: list[LuckyBoardOutcomeOut]
    # Pool cosmetics + badge the player doesn't own yet (paid «Бутса»).
    cosmetics_left: int


class LuckyBoardTokenOut(BaseModel):
    skill_code: str
    skill_name: str
    skill_icon: str
    quantity: int


class LuckyBoardPrizeOut(BaseModel):
    coins: int = 0
    tokens: list[LuckyBoardTokenOut] = []
    shards: int = 0
    # Tokens assembled from shards by this spin.
    crafted_tokens: list[LuckyBoardTokenOut] = []
    cosmetic: Optional[CosmeticOut] = None
    badge: Optional[BadgeOut] = None
    # Admin «Без наград за игры»: a free spin shows its outcome but pays nothing.
    blocked: bool = False


class LuckyBoardSpinOut(BaseModel):
    id: int
    source: str
    outcome: str
    label: str
    reels: list[str]
    prize: LuckyBoardPrizeOut
    new_balance: int
    status: LuckyBoardStatusOut
