from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity
from app.schemas.card import UserCardOut


class CardUpgradeRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_rarity: Rarity
    to_rarity: Rarity
    success_chance: float
    coin_cost: int
    is_active: bool


class CardUpgradeRuleUpdate(BaseModel):
    success_chance: Optional[float] = Field(default=None, ge=0, le=1)
    coin_cost: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class UpgradeCardRequest(BaseModel):
    to_rarity: Rarity
    idempotency_key: Optional[str] = None


class CardUpgradeResultOut(BaseModel):
    success: bool
    from_rarity: Rarity
    to_rarity: Rarity
    coin_cost: int
    new_card: Optional[UserCardOut] = None
    new_balance: int
