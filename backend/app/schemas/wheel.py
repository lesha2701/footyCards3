from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity, WheelPrizePool, WheelPrizeType
from app.schemas.badge import BadgeOut
from app.schemas.pack import CollectionRewardGrantOut, OpenedCardOut, PackOpenResult, PackOut


class WheelPrizeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prize_type: WheelPrizeType
    pool: WheelPrizePool = WheelPrizePool.regular
    weight: int
    is_active: bool
    sort_order: int
    coins_amount: Optional[int] = None
    pack_id: Optional[int] = None
    pack: Optional[PackOut] = None
    card_rarity: Optional[Rarity] = None
    badge_id: Optional[int] = None
    badge: Optional[BadgeOut] = None


class WheelPrizeCreate(BaseModel):
    prize_type: WheelPrizeType
    pool: WheelPrizePool = WheelPrizePool.regular
    weight: int = Field(default=1, ge=1)
    coins_amount: Optional[int] = Field(default=None, ge=0)
    pack_id: Optional[int] = None
    card_rarity: Optional[Rarity] = None
    badge_id: Optional[int] = None
    is_active: bool = True
    sort_order: int = 0


class WheelPrizeUpdate(BaseModel):
    prize_type: Optional[WheelPrizeType] = None
    pool: Optional[WheelPrizePool] = None
    weight: Optional[int] = Field(default=None, ge=1)
    coins_amount: Optional[int] = Field(default=None, ge=0)
    pack_id: Optional[int] = None
    card_rarity: Optional[Rarity] = None
    badge_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class WheelStatusOut(BaseModel):
    free_spins_remaining: int
    free_spins_total: int
    next_free_spin_reset_at: datetime
    spin_cost_coins: int
    spin_cost_stars: int
    prizes: list[WheelPrizeOut]


class WheelSpinResultOut(BaseModel):
    prize: WheelPrizeOut
    new_balance: int
    pack_result: Optional[PackOpenResult] = None
    card_result: Optional[OpenedCardOut] = None
    badge_result: Optional[BadgeOut] = None
    duplicate_badge_coins: Optional[int] = None
    collection_rewards: list[CollectionRewardGrantOut] = []


class WheelPoolPrizeValueOut(BaseModel):
    prize_id: int
    probability: float
    # Coin-equivalent value used for the expected-value estimate (coins =
    # amount, card = average quick-sell of that rarity, pack = the pack's
    # expected quick-sell, badge = the duplicate-badge compensation).
    value_coins: float


class WheelPoolSummaryOut(BaseModel):
    pool: WheelPrizePool
    active_prizes: int
    total_weight: int
    expected_value_coins: float
    prizes: list[WheelPoolPrizeValueOut]


class WheelPoolsSummaryOut(BaseModel):
    pools: list[WheelPoolSummaryOut]
    # The coin price of one paid regular spin — a natural yardstick for
    # "how generous is this pool".
    regular_spin_cost_coins: int
    # «21»: outcome probabilities per paid entry (draws replayed, so they're
    # folded out), from a simulation of a sensible hit/stand strategy —
    # see blackjack_service.OUTCOME_ESTIMATE.
    blackjack_p_jackpot: float
    blackjack_p_golden: float
    blackjack_p_loss: float
    blackjack_consolation_coins: int
    blackjack_expected_value_coins: float
