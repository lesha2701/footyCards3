from pydantic import BaseModel, Field

from app.models.enums import Rarity
from app.schemas.club_squad import ClubCardOut


class SurplusCardOut(BaseModel):
    card: ClubCardOut
    # In any of the club's 5 lineup templates — never sold or exchanged.
    protected: bool
    sell_value: int


class SurplusExchangeOptionOut(BaseModel):
    rarity: Rarity
    target_rarity: Rarity
    available: int


class ClubSurplusOut(BaseModel):
    enabled: bool
    can_manage: bool
    budget: int
    sell_pct: int
    exchange_count: int
    cards: list[SurplusCardOut]
    exchange_options: list[SurplusExchangeOptionOut]


class SurplusCardIdsIn(BaseModel):
    card_ids: list[int] = Field(min_length=1, max_length=200)


class SurplusSellOut(BaseModel):
    sold: int
    coins: int
    budget: int


class SurplusExchangeOut(BaseModel):
    card: ClubCardOut
    budget: int
