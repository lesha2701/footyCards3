from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity
from app.schemas.badge import BadgeOut
from app.schemas.card import UserCardOut
from app.schemas.coach import CoachOut


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
    stars_price: Optional[int] = None
    bonus_coins: Optional[int] = None
    badge_id: Optional[int] = None
    badge: Optional[BadgeOut] = None
    image_path: Optional[str]
    card_count: int
    guaranteed_min_rarity: Optional[Rarity]
    is_active: bool
    purchase_limit_per_user: Optional[int]
    available_from: Optional[datetime]
    available_until: Optional[datetime]
    rarity_probabilities: list[PackRarityProbabilityOut]
    coach_drop_chance: float
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
    stars_price: Optional[int] = Field(default=None, ge=1)
    bonus_coins: Optional[int] = Field(default=None, ge=1)
    badge_id: Optional[int] = None
    card_count: int = Field(ge=1, le=12)
    guaranteed_min_rarity: Optional[Rarity] = None
    is_active: bool = True
    image_path: Optional[str] = None
    purchase_limit_per_user: Optional[int] = Field(default=None, ge=1)
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    rarity_probabilities: list[PackRarityProbabilityIn]
    coach_drop_chance: float = Field(default=0.0, ge=0, le=1)


class PackUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    stars_price: Optional[int] = Field(default=None, ge=1)
    bonus_coins: Optional[int] = Field(default=None, ge=1)
    badge_id: Optional[int] = None
    card_count: Optional[int] = Field(default=None, ge=1, le=12)
    guaranteed_min_rarity: Optional[Rarity] = None
    is_active: Optional[bool] = None
    image_path: Optional[str] = None
    purchase_limit_per_user: Optional[int] = Field(default=None, ge=1)
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    rarity_probabilities: Optional[list[PackRarityProbabilityIn]] = None
    coach_drop_chance: Optional[float] = Field(default=None, ge=0, le=1)


class UserCoachCardOut(BaseModel):
    """One personal user-owned coach card — mirrors the club-side
    ClubCoachCardOut exactly, substituting personal coach models."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    serial_number: int
    coach: CoachOut
    acquired_at: datetime


class OpenedCardOut(BaseModel):
    card: UserCardOut
    is_new: bool
    duplicate_count: int


class OpenedCoachCardOut(BaseModel):
    card: UserCoachCardOut
    is_new: bool
    duplicate_count: int


class CollectionRewardGrantOut(BaseModel):
    collection_id: int
    collection_name: str
    reward_coins: int
    granted_pack: Optional["PackOpenResult"] = None


class PackOpenResult(BaseModel):
    opening_id: int
    pack: PackOut
    cards: list[OpenedCardOut]
    coach_cards: list[OpenedCoachCardOut] = []
    new_balance: int
    referral_bonus_coins: Optional[int] = None
    collection_rewards: list[CollectionRewardGrantOut] = []


class OpenPackRequest(BaseModel):
    idempotency_key: Optional[str] = None


class OpenPackBulkRequest(BaseModel):
    quantity: int = Field(ge=1, le=100)
    idempotency_key: Optional[str] = None


class PackBulkOpenResult(BaseModel):
    pack: PackOut
    quantity: int
    opening_ids: list[int]
    cards: list[OpenedCardOut]
    coach_cards: list[OpenedCoachCardOut] = []
    new_balance: int
    total_price_paid: int
    referral_bonus_coins: Optional[int] = None
    collection_rewards: list[CollectionRewardGrantOut] = []


CollectionRewardGrantOut.model_rebuild()
