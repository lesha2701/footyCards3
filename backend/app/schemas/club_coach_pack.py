from pydantic import BaseModel, ConfigDict

from app.models.enums import Rarity
from app.schemas.club_squad import ClubCoachCardOut


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
    image_path: str | None
    is_active: bool
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
