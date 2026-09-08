from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.club_pack import ClubPackOut
from app.schemas.club_squad import ClubCardOut, ClubCoachCardOut


class OpenedClubPackItemOut(BaseModel):
    kind: Literal["player", "coach"]
    card: Optional[ClubCardOut] = None
    coach_card: Optional[ClubCoachCardOut] = None
    is_new: bool


class ClubPackOpenResult(BaseModel):
    opening_id: int
    pack: ClubPackOut
    cards: list[OpenedClubPackItemOut]
    new_budget: int


class OpenClubPackRequest(BaseModel):
    idempotency_key: str | None = None
