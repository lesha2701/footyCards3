from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.club_pack import ClubPackOut
from app.schemas.club_squad import ClubCardOut


class SurplusCardOut(BaseModel):
    card: ClubCardOut
    # In any of the club's 5 lineup templates — never sold or exchanged.
    protected: bool
    sell_value: int


class ClubSurplusOut(BaseModel):
    enabled: bool
    can_manage: bool
    budget: int
    sell_pct: int
    exchange_count: int
    cards: list[SurplusCardOut]
    # The club pack `exchange_count` spare cards are burned for (None: no active pack).
    exchange_pack: Optional[ClubPackOut] = None


class SurplusCardIdsIn(BaseModel):
    card_ids: list[int] = Field(min_length=1, max_length=200)


class SurplusSellOut(BaseModel):
    sold: int
    coins: int
    budget: int

