from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity
from app.schemas.card import UserCardOut


class PackRarityProbabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rarity: Rarity
    probability: float


class PackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str
    price: int
    image_path: Optional[str]
    card_count: int
    guaranteed_min_rarity: Optional[Rarity]
    is_active: bool
    purchase_limit_per_user: Optional[int]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    rarity_probabilities: list[PackRarityProbabilityOut]
    user_purchase_count: int = 0
    is_available_now: bool = True


class PackRarityProbabilityIn(BaseModel):
    rarity: Rarity
    probability: float = Field(ge=0, le=1)


class PackCreate(BaseModel):
    slug: str
    name: str
    description: str = ""
    price: int = Field(ge=0)
    card_count: int = Field(ge=1, le=12)
    guaranteed_min_rarity: Optional[Rarity] = None
    is_active: bool = True
    image_path: Optional[str] = None
    purchase_limit_per_user: Optional[int] = Field(default=None, ge=1)
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    rarity_probabilities: list[PackRarityProbabilityIn]


class PackUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    card_count: Optional[int] = Field(default=None, ge=1, le=12)
    guaranteed_min_rarity: Optional[Rarity] = None
    is_active: Optional[bool] = None
    image_path: Optional[str] = None
    purchase_limit_per_user: Optional[int] = Field(default=None, ge=1)
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    rarity_probabilities: Optional[list[PackRarityProbabilityIn]] = None


class OpenedCardOut(BaseModel):
    card: UserCardOut
    is_new: bool
    duplicate_count: int


class PackOpenResult(BaseModel):
    opening_id: int
    pack: PackOut
    cards: list[OpenedCardOut]
    new_balance: int


class OpenPackRequest(BaseModel):
    idempotency_key: Optional[str] = None
