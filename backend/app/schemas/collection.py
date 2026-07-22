from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import CardSource, Position, Rarity
from app.schemas.player import PlayerOut


class UserCardListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    serial_number: int
    player: PlayerOut
    acquired_at: datetime
    source: CardSource
    is_locked_by_admin: bool
    is_locked_in_trade: bool
    is_in_lineup: bool
    duplicate_count: int = 1


SortBy = Literal["rating", "rarity", "acquired_at"]
SortDir = Literal["asc", "desc"]


class CollectionFilterParams:
    def __init__(
        self,
        rarity: Optional[List[Rarity]] = None,
        country: Optional[str] = None,
        club: Optional[str] = None,
        position: Optional[Position] = None,
        min_rating: Optional[int] = None,
        max_rating: Optional[int] = None,
        search: Optional[str] = None,
        sort_by: SortBy = "acquired_at",
        sort_dir: SortDir = "desc",
    ):
        self.rarity = rarity
        self.country = country
        self.club = club
        self.position = position
        self.min_rating = min_rating
        self.max_rating = max_rating
        self.search = search
        self.sort_by = sort_by
        self.sort_dir = sort_dir


class SellCardRequest(BaseModel):
    user_card_id: int
    confirm_last_copy: bool = False


class BulkSellRequest(BaseModel):
    user_card_ids: List[int]
    confirm_last_copy: bool = False


class SellResultOut(BaseModel):
    sold_count: int
    coins_earned: int
    new_balance: int
