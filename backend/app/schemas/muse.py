from typing import Optional

from pydantic import BaseModel, Field


class MuseActivateIn(BaseModel):
    # None = no active Muse.
    muse_id: Optional[int] = None


class MuseSellSpareIn(BaseModel):
    count: int = Field(default=1, ge=1, le=1000)


class MuseGiftIn(BaseModel):
    accessory_id: int
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class MuseGiftInvoiceIn(BaseModel):
    accessory_id: int


class MuseCollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True
    sort_order: int = 0


class MuseIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    title: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    icon: str = Field(default="💃", max_length=16)
    rarity: str = "common"
    collection_id: Optional[int] = None
    effect: str = "daily_coins"
    effect_value: int = Field(default=100, ge=0, le=100_000)
    drop_weight: int = Field(default=100, ge=0, le=100_000)
    is_active: bool = True
    sort_order: int = 0


class MuseAccessoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    icon: str = Field(default="👜", max_length=16)
    kind: str = "other"
    rarity: str = "common"
    boost_pct: int = Field(default=10, ge=0, le=500)
    coins_price: int = Field(default=0, ge=0, le=10_000_000)
    stars_price: int = Field(default=0, ge=0, le=100_000)
    is_active: bool = True
    sort_order: int = 0


class MuseGrantIn(BaseModel):
    user_id: int
