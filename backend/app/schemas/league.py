from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LeagueTierOut(BaseModel):
    """Admin-facing shape — raw reward_pack_id, matching TaskDefinitionOut's
    precedent (the admin UI cross-references its own already-fetched packs
    list, it doesn't need a resolved name)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    min_rating: int
    icon: str
    reward_coins: int
    reward_pack_id: Optional[int] = None
    sort_order: int


class LeagueTierPublicOut(BaseModel):
    """Player-facing shape — resolved reward_pack_name instead of a raw id,
    matching TaskOut's precedent."""

    id: int
    name: str
    min_rating: int
    icon: str
    reward_coins: int
    reward_pack_name: Optional[str] = None
    sort_order: int


class LeagueTierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    min_rating: int = Field(ge=0)
    icon: str = Field(default="🏅", min_length=1, max_length=16)
    reward_coins: int = Field(default=0, ge=0)
    reward_pack_id: Optional[int] = None
    sort_order: int = 0


class LeagueTierUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    min_rating: Optional[int] = Field(default=None, ge=0)
    icon: Optional[str] = Field(default=None, min_length=1, max_length=16)
    reward_coins: Optional[int] = Field(default=None, ge=0)
    reward_pack_id: Optional[int] = None
    sort_order: Optional[int] = None


class LeagueStatusOut(BaseModel):
    total_rating: int
    arena_rating: int
    tactics_rating: int
    penalty_rating: int
    current_league: Optional[LeagueTierPublicOut] = None
    next_league: Optional[LeagueTierPublicOut] = None
    points_to_next: Optional[int] = None


class LeagueBackfillResultOut(BaseModel):
    rewarded_count: int
