from pydantic import BaseModel, ConfigDict, Field


class BadgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon: str
    image_path: str | None = None
    is_active: bool
    sort_order: int


class BadgeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    icon: str = Field(min_length=1, max_length=16)
    is_active: bool = True
    sort_order: int = 0


class BadgeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    icon: str | None = Field(default=None, min_length=1, max_length=16)
    is_active: bool | None = None
    sort_order: int | None = None
