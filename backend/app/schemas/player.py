from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Position, Rarity


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    display_name: str
    rating: int
    rarity: Rarity
    country: str
    club: str
    position: Position
    image_path: Optional[str]
    quick_sell_price: int
    is_active: bool


class PlayerCreate(BaseModel):
    first_name: str
    last_name: str
    display_name: str
    rating: int = Field(ge=1, le=99)
    rarity: Rarity
    country: str
    club: str
    position: Position
    quick_sell_price: int = Field(ge=0, default=10)
    is_active: bool = True


class PlayerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=99)
    rarity: Optional[Rarity] = None
    country: Optional[str] = None
    club: Optional[str] = None
    position: Optional[Position] = None
    quick_sell_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
