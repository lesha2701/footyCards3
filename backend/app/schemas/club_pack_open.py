from app.schemas.club_pack import ClubPackOut
from app.schemas.club_squad import ClubCardOut
from pydantic import BaseModel


class OpenedClubCardOut(BaseModel):
    card: ClubCardOut
    is_new: bool


class ClubPackOpenResult(BaseModel):
    opening_id: int
    pack: ClubPackOut
    cards: list[OpenedClubCardOut]
    new_budget: int


class OpenClubPackRequest(BaseModel):
    idempotency_key: str | None = None
