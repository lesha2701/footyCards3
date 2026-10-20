from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Position, Rarity

_PLAYER_COLUMN_FIELDS = (
    "id", "first_name", "last_name", "display_name", "rating", "rarity",
    "country", "club", "position", "image_path", "quick_sell_price", "is_active",
    "is_pack_droppable", "collection_id", "path_talent_code",
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
    is_pack_droppable: bool
    collection_id: Optional[int] = None
    collection_name: Optional[str] = None
    # «Академия»: set = a path card with this talent (services/path_talent_catalog.py).
    path_talent_code: Optional[str] = None

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
        result = {name: getattr(data, name, None) for name in _PLAYER_COLUMN_FIELDS}
        collection = getattr(data, "collection", None)
        result["collection_name"] = collection.name if collection is not None else None
        result["attack_rating"] = data.attack_rating if data.attack_rating is not None else data.rating
        result["defense_rating"] = data.defense_rating if data.defense_rating is not None else data.rating
        return result


def split_display_name(display_name: str) -> tuple[str, str]:
    """first_name / last_name from the display name — the admin only edits
    the display name now; the two legacy NOT NULL columns follow it. One
    word fills both («Пеле» → «Пеле», «Пеле»); longer names split after the
    first word («Лионель Месси» → «Лионель», «Месси»)."""
    parts = display_name.strip().split(maxsplit=1)
    if not parts:
        return "", ""
    first = parts[0][:64]
    last = (parts[1] if len(parts) > 1 else parts[0])[:64]
    return first, last


def _fill_names_from_display(data):
    """Before-validator for create/update: blank first/last names follow the
    display name (older clients and CSV files may still send them)."""
    if not isinstance(data, dict) or not (data.get("display_name") or "").strip():
        return data
    if (data.get("first_name") or "").strip() and (data.get("last_name") or "").strip():
        return data
    first, last = split_display_name(data["display_name"])
    return {**data, "first_name": first, "last_name": last}


class PlayerCreate(BaseModel):
    first_name: str = ""
    last_name: str = ""
    display_name: str = Field(min_length=1)


    @model_validator(mode="before")
    @classmethod
    def _names(cls, data):
        return _fill_names_from_display(data)
    rating: int = Field(ge=1, le=99)
    attack_rating: Optional[int] = Field(default=None, ge=1, le=99)
    defense_rating: Optional[int] = Field(default=None, ge=1, le=99)
    rarity: Rarity
    country: str
    club: str
    position: Position
    quick_sell_price: int = Field(ge=0, default=10)
    is_active: bool = True
    is_pack_droppable: bool = True
    collection_id: Optional[int] = None
    path_talent_code: Optional[str] = None


class PlayerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = Field(default=None, min_length=1)


    @model_validator(mode="before")
    @classmethod
    def _names(cls, data):
        return _fill_names_from_display(data)
    rating: Optional[int] = Field(default=None, ge=1, le=99)
    attack_rating: Optional[int] = Field(default=None, ge=1, le=99)
    defense_rating: Optional[int] = Field(default=None, ge=1, le=99)
    rarity: Optional[Rarity] = None
    country: Optional[str] = None
    club: Optional[str] = None
    position: Optional[Position] = None
    quick_sell_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    is_pack_droppable: Optional[bool] = None
    collection_id: Optional[int] = None
    path_talent_code: Optional[str] = None
