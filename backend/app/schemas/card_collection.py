from typing import Optional

from pydantic import BaseModel, ConfigDict


class CardCollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    is_active: bool
    sort_order: int


class CardCollectionCreate(BaseModel):
    name: str
    description: str = ""
    is_active: bool = True
    sort_order: int = 0


class CardCollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CardCollectionPublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
