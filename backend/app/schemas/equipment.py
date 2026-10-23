from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EquipmentBuyIn(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class EquipmentEquipIn(BaseModel):
    copy_id: int
    user_card_id: int


class EquipmentUnequipIn(BaseModel):
    copy_id: int


class EquipmentItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    icon: str = Field(default="👕", max_length=16)
    slot: str
    rarity: str = "common"
    collection_id: Optional[int] = None
    effect: str = "rating"
    effect_value: int = Field(default=1, ge=0, le=20)
    cond_club: Optional[str] = Field(default=None, max_length=64)
    cond_country: Optional[str] = Field(default=None, max_length=64)
    coins_price: int = Field(default=0, ge=0, le=10_000_000)
    stars_price: int = Field(default=0, ge=0, le=100_000)
    is_active: bool = True
    sort_order: int = 0
    max_supply: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None


class EquipmentCollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    set_size: int = Field(default=3, ge=1, le=6)
    set_bonus_rating: int = Field(default=1, ge=0, le=10)
    set_team_country: Optional[str] = Field(default=None, max_length=64)
    set_team_chemistry: int = Field(default=0, ge=0, le=3)
    is_active: bool = True
    sort_order: int = 0


class EquipmentGrantIn(BaseModel):
    user_id: int
