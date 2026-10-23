from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.club_pack import ClubPackOut
from app.schemas.club_squad import ClubCardOut, ClubCoachCardOut, ClubStadiumCardOut


class OpenedClubPackItemOut(BaseModel):
    kind: Literal["player", "coach", "stadium"]
    card: Optional[ClubCardOut] = None
    coach_card: Optional[ClubCoachCardOut] = None
    stadium_card: Optional[ClubStadiumCardOut] = None
    is_new: bool


class ClubPackOpenResult(BaseModel):
    opening_id: int
    pack: ClubPackOut
    cards: list[OpenedClubPackItemOut]
    new_budget: int


class OpenClubPackRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=100)
    # Several copies at once: one budget debit, one transaction.
    quantity: int = Field(default=1, ge=1, le=20)
