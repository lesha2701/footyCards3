from datetime import datetime

from pydantic import BaseModel

from app.schemas.player import PlayerOut


class ClubCardOut(BaseModel):
    id: int
    serial_number: int
    player: PlayerOut
    acquired_at: datetime
    is_in_lineup: bool


class ClubLineupSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    card: ClubCardOut | None = None


class ClubLineupOut(BaseModel):
    is_complete: bool
    team_strength: int | None
    slots: list[ClubLineupSlotOut]


class ClubLineupSlotIn(BaseModel):
    slot_code: str
    club_card_id: int


class ClubLineupSetRequest(BaseModel):
    slots: list[ClubLineupSlotIn]
