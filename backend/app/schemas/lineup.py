from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.card import UserCardOut


class LineupSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    card: Optional[UserCardOut] = None


class LineupOut(BaseModel):
    id: Optional[int] = None
    formation: str
    is_complete: bool
    team_strength: Optional[int] = None
    slots: list[LineupSlotOut]


class LineupSlotIn(BaseModel):
    slot_code: str
    user_card_id: int


class LineupSetRequest(BaseModel):
    slots: list[LineupSlotIn]
