from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class CardCollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    is_active: bool
    sort_order: int
    image_path: Optional[str]
    reward_coins: int
    reward_pack_id: Optional[int]


class CardCollectionCreate(BaseModel):
    name: str
    description: str = ""
    is_active: bool = True
    sort_order: int = 0
    image_path: Optional[str] = None
    reward_coins: int = 0
    reward_pack_id: Optional[int] = None


class CardCollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    image_path: Optional[str] = None
    reward_coins: Optional[int] = None
    reward_pack_id: Optional[int] = None


class CardCollectionPublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SetCollectionPlayersRequest(BaseModel):
    player_ids: List[int]
