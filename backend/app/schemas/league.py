from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class LeagueTierOut(BaseModel):
    """Admin-facing shape — raw reward_pack_id, matching TaskDefinitionOut's
    precedent (the admin UI cross-references its own already-fetched packs
    list, it doesn't need a resolved name)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    min_rating: int
    color: str
    image_path: Optional[str] = None
    reward_coins: int
    reward_pack_id: Optional[int] = None
    sort_order: int


class LeagueTierPublicOut(BaseModel):
    """Player-facing shape — resolved reward_pack_name instead of a raw id,
    matching TaskOut's precedent."""

    id: int
    name: str
    min_rating: int
    color: str
    image_path: Optional[str] = None
    reward_coins: int
    reward_pack_name: Optional[str] = None
    sort_order: int


class LeagueTierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    min_rating: int = Field(ge=0)
    color: str = Field(default="#94a3b8", pattern=_COLOR_PATTERN)
    reward_coins: int = Field(default=0, ge=0)
    reward_pack_id: Optional[int] = None
    sort_order: int = 0


class LeagueTierUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    min_rating: Optional[int] = Field(default=None, ge=0)
    color: Optional[str] = Field(default=None, pattern=_COLOR_PATTERN)
    reward_coins: Optional[int] = Field(default=None, ge=0)
    reward_pack_id: Optional[int] = None
    sort_order: Optional[int] = None


class LeagueRewardClaimOut(BaseModel):
    """One not-yet-visually-acknowledged reward — see
    league_service.mark_rewards_seen. reward_coins/reward_pack_name reflect
    what was actually granted (snapshotted at claim time), not the tier's
    current nominal reward."""

    id: int
    tier_name: str
    color: str
    image_path: Optional[str] = None
    reward_coins: int
    reward_pack_name: Optional[str] = None
    granted_at: datetime


class LeagueStatusOut(BaseModel):
    total_rating: int
    arena_rating: int
    tactics_rating: int
    penalty_rating: int
    current_league: Optional[LeagueTierPublicOut] = None
    next_league: Optional[LeagueTierPublicOut] = None
    points_to_next: Optional[int] = None
    # Share of eligible players (non-banned, non-admin) whose own
    # floor-adjusted league matches current_league — None when there's no
    # current league (below the lowest tier, or no tiers configured).
    current_league_percent: Optional[float] = None
    unseen_rewards: list[LeagueRewardClaimOut] = Field(default_factory=list)


class LeagueBackfillResultOut(BaseModel):
    rewarded_count: int
