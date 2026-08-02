from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Position, Rarity

_PLAYER_COLUMN_FIELDS = (
    "id", "first_name", "last_name", "display_name", "rating", "rarity",
    "country", "club", "position", "image_path", "quick_sell_price", "is_active",
    "collection_id",
)


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    display_name: str
    rating: int
    attack_rating: int
    defense_rating: int
    rarity: Rarity
    country: str
    club: str
    position: Position
    image_path: Optional[str]
    quick_sell_price: int
    is_active: bool
    collection_id: Optional[int] = None
    collection_name: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _derive_collection_name(cls, data):
        """Derives `collection_name` from the ORM object's `collection`
        relationship (Player.collection has lazy="joined", so it's always
        already loaded), and falls back attack_rating/defense_rating to
        `rating` for any row that predates those columns (NULL until
        backend/app/backfill_player_stats.py fills it in). Runs for every
        validation of this schema, including when it's nested inside another
        schema (UserCardOut.player, OpenedCardOut.card.player, etc.), so this
        fixes both concerns everywhere at once instead of per call site."""
        if isinstance(data, dict):
            return data
        result = {name: getattr(data, name) for name in _PLAYER_COLUMN_FIELDS}
        collection = getattr(data, "collection", None)
        result["collection_name"] = collection.name if collection is not None else None
        result["attack_rating"] = data.attack_rating if data.attack_rating is not None else data.rating
        result["defense_rating"] = data.defense_rating if data.defense_rating is not None else data.rating
        return result


class PlayerCreate(BaseModel):
    first_name: str
    last_name: str
    display_name: str
    rating: int = Field(ge=1, le=99)
    attack_rating: Optional[int] = Field(default=None, ge=1, le=99)
    defense_rating: Optional[int] = Field(default=None, ge=1, le=99)
    rarity: Rarity
    country: str
    club: str
    position: Position
    quick_sell_price: int = Field(ge=0, default=10)
    is_active: bool = True
    collection_id: Optional[int] = None


class PlayerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=99)
    attack_rating: Optional[int] = Field(default=None, ge=1, le=99)
    defense_rating: Optional[int] = Field(default=None, ge=1, le=99)
    rarity: Optional[Rarity] = None
    country: Optional[str] = None
    club: Optional[str] = None
    position: Optional[Position] = None
    quick_sell_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    collection_id: Optional[int] = None
