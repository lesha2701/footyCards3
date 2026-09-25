from pydantic import BaseModel, Field

from app.schemas.lineup import EquippedCoachOut
from app.schemas.player import PlayerOut


class PersonalSquadSlotIn(BaseModel):
    slot_code: str
    user_card_id: int


class PersonalSquadSetRequest(BaseModel):
    slots: list[PersonalSquadSlotIn]


class PersonalSquadTacticsRequest(BaseModel):
    formation: str
    mentality: str
    playstyle: str


class PersonalSquadCoachRequest(BaseModel):
    user_coach_card_id: int | None = None


class PersonalSquadRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PersonalSquadSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    user_card_id: int | None = None
    serial_number: int | None = None
    player: PlayerOut | None = None


class PersonalSquadOut(BaseModel):
    template_index: int
    name: str
    is_active: bool
    is_complete: bool
    formation: str
    mentality: str
    playstyle: str
    slots: list[PersonalSquadSlotOut]
    coach: EquippedCoachOut | None = None
