from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TrophyDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str
    icon: str
    image_path: Optional[str] = None
    is_active: bool
    sort_order: int


class TrophyDefinitionCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    icon: str = Field(default="🏆", min_length=1, max_length=16)
    is_active: bool = True
    sort_order: int = 0


class TrophyDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    icon: Optional[str] = Field(default=None, min_length=1, max_length=16)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class UserTrophyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trophy: TrophyDefinitionOut
    message: Optional[str] = None
    granted_at: datetime
    granted_by_admin_id: Optional[int] = None
