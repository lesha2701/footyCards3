from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity
from app.schemas.card import UserCardOut

# Mirrors MAX_STAKED_CARDS in schemas/card_upgrade.py — same UX/sanity
# ceiling on how many material cards one feed request can name.
MAX_MATERIAL_CARDS = 200


class DiamondUpgradeTierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    min_rating: int
    max_rating: int
    # None means that rarity cannot be used to level up a card in this band.
    common_cost: Optional[int]
    rare_cost: Optional[int]
    epic_cost: Optional[int]
    legendary_cost: Optional[int]
    is_active: bool


class DiamondUpgradeTierCreate(BaseModel):
    min_rating: int = Field(ge=1, le=99)
    max_rating: int = Field(ge=1, le=99)
    common_cost: Optional[int] = Field(default=None, ge=1)
    rare_cost: Optional[int] = Field(default=None, ge=1)
    epic_cost: Optional[int] = Field(default=None, ge=1)
    legendary_cost: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True


class DiamondUpgradeTierUpdate(BaseModel):
    min_rating: Optional[int] = Field(default=None, ge=1, le=99)
    max_rating: Optional[int] = Field(default=None, ge=1, le=99)
    # Sending an explicit null clears the cost (rarity becomes unavailable);
    # omitting the field entirely leaves it unchanged (see exclude_unset in
    # the admin router).
    common_cost: Optional[int] = Field(default=None, ge=1)
    rare_cost: Optional[int] = Field(default=None, ge=1)
    epic_cost: Optional[int] = Field(default=None, ge=1)
    legendary_cost: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


class FeedCardsRequest(BaseModel):
    diamond_card_id: int
    material_card_ids: list[int] = Field(min_length=1, max_length=MAX_MATERIAL_CARDS)


class FeedCardsResult(BaseModel):
    diamond_card: UserCardOut
    material_rarity: Rarity
    cards_consumed: int
    cards_returned: int
    rating_gained: int


class DiamondRatingCapOut(BaseModel):
    cap: int


class DiamondMaterialCardsOut(BaseModel):
    # "admin_tier" means the ordinary per-rarity /upgrade-cards flow applies
    # (cards is always [] for it); the two extension bands are diamond-only.
    kind: Literal["admin_tier", "any_diamond", "same_player_diamond"]
    cost: Optional[int]
    ceiling: int
    cards: list[UserCardOut]
