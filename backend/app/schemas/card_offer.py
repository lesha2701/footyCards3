from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.player import PlayerOut


class CardOfferOut(BaseModel):
    """A card on sale for Stars, as the shop shows it."""

    id: int
    player: PlayerOut
    stars_price: int
    title: Optional[str] = None
    ends_at: Optional[datetime] = None
    stock: Optional[int] = None
    left: Optional[int] = None  # copies left (None = unlimited)
    per_user_limit: int = 1  # 0 = unlimited
    bought: int = 0  # by this player
    can_buy: bool = True
    retired: bool = False  # no longer drops from packs


class CardOfferAdminIn(BaseModel):
    player_id: int
    stars_price: int = Field(ge=1, le=100_000)
    title: Optional[str] = Field(default=None, max_length=64)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    stock: Optional[int] = Field(default=None, ge=1)
    per_user_limit: int = Field(default=1, ge=0, le=1000)
    is_active: bool = True
    sort_order: int = 0


class CardOfferAdminOut(BaseModel):
    id: int
    player: PlayerOut
    stars_price: int
    title: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    stock: Optional[int] = None
    per_user_limit: int
    sold_count: int
    is_active: bool
    sort_order: int
    live: bool  # on sale right now
