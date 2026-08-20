from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity
from app.schemas.card import UserCardOut

# Hardcoded UX/sanity bound on how many cards one attempt can stake — not an
# economy lever (those are extra_card_bonus/max_success_chance below), just
# a reasonable ceiling on request size.
MAX_STAKED_CARDS = 10


class CardUpgradeRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_rarity: Rarity
    to_rarity: Rarity
    success_chance: float
    coin_cost: int
    is_active: bool
    extra_card_bonus: float
    max_success_chance: float


class CardUpgradeRuleUpdate(BaseModel):
    success_chance: Optional[float] = Field(default=None, ge=0, le=1)
    coin_cost: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    extra_card_bonus: Optional[float] = Field(default=None, ge=0, le=1)
    max_success_chance: Optional[float] = Field(default=None, ge=0, le=1)


class UpgradeCardRequest(BaseModel):
    user_card_ids: list[int] = Field(min_length=1, max_length=MAX_STAKED_CARDS)
    to_rarity: Rarity
    idempotency_key: Optional[str] = None


class CardUpgradeResultOut(BaseModel):
    success: bool
    from_rarity: Rarity
    to_rarity: Rarity
    card_count: int
    success_chance: float
    coin_cost: int
    new_card: Optional[UserCardOut] = None
    new_balance: int
