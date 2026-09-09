from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.card import UserCardOut
from app.schemas.coach import CoachBoostOut
from app.schemas.pack import UserCoachCardOut


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


class LineupOut(BaseModel):
    id: Optional[int] = None
    formation: str
    tactic: str
    is_complete: bool
    team_strength: Optional[int] = None
    max_diamond: int
    coach: Optional[EquippedCoachOut] = None
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
