from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity


class ClubPackRarityProbabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rarity: Rarity
    probability: float


class ClubPackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name: str
    description: str
    price: int
    card_count: int
    guaranteed_min_rarity: Optional[Rarity]
    image_path: Optional[str]
    is_active: bool
    sort_order: int
    rarity_probabilities: list[ClubPackRarityProbabilityOut]


class ClubPackRarityProbabilityIn(BaseModel):
    rarity: Rarity
    probability: float = Field(ge=0, le=1)


class ClubPackCreate(BaseModel):
    slug: str
    name: str
    description: str = ""
    price: int = Field(ge=0)
    card_count: int = Field(default=3, ge=1, le=10)
    guaranteed_min_rarity: Optional[Rarity] = None
    rarity_probabilities: list[ClubPackRarityProbabilityIn]
    is_active: bool = True
    sort_order: int = 0


class ClubPackUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = Field(default=None, ge=0)
    card_count: Optional[int] = Field(default=None, ge=1, le=10)
    guaranteed_min_rarity: Optional[Rarity] = None
    rarity_probabilities: Optional[list[ClubPackRarityProbabilityIn]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
