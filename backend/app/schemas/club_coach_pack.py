from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Rarity
from app.schemas.club_squad import ClubCoachCardOut


def _reject_diamond(rarity: Optional[Rarity]) -> Optional[Rarity]:
    # Coach carries ck_coaches_rarity_not_diamond — a pack advertising
    # "diamond" odds (rarity_probabilities) or a "diamond" guaranteed
    # minimum could never actually be fulfilled by pick_random_coach,
    # silently violating the pack's own contract.
    if rarity == Rarity.diamond:
        raise ValueError("Coach packs cannot reference the 'diamond' rarity — coaches are never diamond")
    return rarity


class ClubCoachPackRarityProbabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rarity: Rarity
    probability: float


class ClubCoachPackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str
    description: str
    price: int
    card_count: int
    guaranteed_min_rarity: Optional[Rarity]
    image_path: str | None
    is_active: bool
    sort_order: int
    rarity_probabilities: list[ClubCoachPackRarityProbabilityOut]


class OpenedClubCoachCardOut(BaseModel):
    card: ClubCoachCardOut
    is_new: bool


class ClubCoachPackOpenResult(BaseModel):
    pack: ClubCoachPackOut
    cards: list[OpenedClubCoachCardOut]
    new_budget: int


class OpenClubCoachPackRequest(BaseModel):
    idempotency_key: str | None = None


class ClubCoachPackRarityProbabilityIn(BaseModel):
    rarity: Rarity
    probability: float = Field(ge=0, le=1)

    _reject_diamond_rarity = field_validator("rarity")(_reject_diamond)


class ClubCoachPackCreate(BaseModel):
    slug: str
    name: str
    description: str = ""
    price: int = Field(ge=0)
    card_count: int = Field(default=1, ge=1, le=10)
    guaranteed_min_rarity: Optional[Rarity] = None
    rarity_probabilities: list[ClubCoachPackRarityProbabilityIn]
    is_active: bool = True
    sort_order: int = 0

    _reject_diamond_min_rarity = field_validator("guaranteed_min_rarity")(_reject_diamond)


class ClubCoachPackUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    card_count: Optional[int] = Field(default=None, ge=1, le=10)
    guaranteed_min_rarity: Optional[Rarity] = None
    rarity_probabilities: Optional[list[ClubCoachPackRarityProbabilityIn]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

    _reject_diamond_min_rarity = field_validator("guaranteed_min_rarity")(_reject_diamond)
