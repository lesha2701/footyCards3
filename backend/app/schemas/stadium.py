from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Rarity
from app.schemas.coach import _blank_to_none


class StadiumOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rarity: Rarity
    image_path: Optional[str]
    club: Optional[str] = None
    quick_sell_price: int
    is_active: bool
    is_pack_droppable: bool
    boost_pct: float


class StadiumCreate(BaseModel):
    display_name: str
    rarity: Rarity
    # «Домашний стадион»: players of this club get extra chemistry at home.
    club: Optional[str] = Field(default=None, max_length=64)
    quick_sell_price: int = Field(ge=0, default=10)
    is_active: bool = True
    is_pack_droppable: bool = True
    boost_pct: float = Field(ge=0, le=1, default=0.0)

    _club = field_validator("club")(_blank_to_none)


class StadiumUpdate(BaseModel):
    display_name: Optional[str] = None
    rarity: Optional[Rarity] = None
    # "" clears the club (sent explicitly, so exclude_unset keeps it).
    club: Optional[str] = Field(default=None, max_length=64)
    quick_sell_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    is_pack_droppable: Optional[bool] = None
    boost_pct: Optional[float] = Field(default=None, ge=0, le=1)

    _club = field_validator("club")(_blank_to_none)
