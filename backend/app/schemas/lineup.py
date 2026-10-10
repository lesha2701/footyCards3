from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.card import UserCardOut
from app.schemas.coach import CoachBoostOut
from app.schemas.pack import UserCoachCardOut, UserStadiumCardOut


class LineupSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    card: Optional[UserCardOut] = None


class EquippedCoachOut(BaseModel):
    """The coach currently equipped on a personal Card Arena lineup — mirrors
    app.schemas.club_squad.EquippedCoachOut field-for-field, but defined
    locally rather than imported from there so this personal-track schema
    module doesn't depend on a club-track one."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rarity: str
    image_path: Optional[str]
    boosts: list[CoachBoostOut]


class EquippedStadiumOut(BaseModel):
    """The stadium currently equipped on a squad — mirrors EquippedCoachOut's
    shape (id/display_name/rarity/image_path), plus boost_pct since that's
    the whole point of a stadium. Shared across all three squad Out schemas."""

    id: int
    display_name: str
    rarity: str
    image_path: str | None
    boost_pct: float


class LineupOut(BaseModel):
    id: Optional[int] = None
    template_index: int
    name: str
    is_active: bool
    formation: str
    tactic: str
    is_complete: bool
    team_strength: Optional[int] = None
    max_diamond: int
    coach: Optional[EquippedCoachOut] = None
    stadium: Optional[EquippedStadiumOut] = None
    slots: list[LineupSlotOut]


class LineupSlotIn(BaseModel):
    slot_code: str
    user_card_id: int


class LineupSetRequest(BaseModel):
    slots: list[LineupSlotIn]


class LineupTacticRequest(BaseModel):
    tactic: str


class LineupCoachSetRequest(BaseModel):
    user_coach_card_id: Optional[int] = None


class LineupStadiumSetRequest(BaseModel):
    user_stadium_card_id: Optional[int] = None


class LineupRenameRequest(BaseModel):
    name: str


class BenchUpgradeOut(BaseModel):
    """A single-swap squad improvement hint (auto_squad_service.bench_upgrades)."""
    slot_code: str
    current_card_id: Optional[int] = None
    current_name: Optional[str] = None
    current_rating: Optional[int] = None
    suggested_card_id: int
    suggested_name: str
    suggested_rating: int
    gain: int
