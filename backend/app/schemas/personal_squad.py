from pydantic import BaseModel, Field

from app.schemas.chemistry import ChemistryOut
from app.schemas.lineup import EquippedCoachOut, EquippedStadiumOut
from app.schemas.player import PlayerOut


class PersonalSquadSlotIn(BaseModel):
    slot_code: str
    user_card_id: int


class PersonalSquadSetRequest(BaseModel):
    slots: list[PersonalSquadSlotIn]


class PersonalSquadTacticsRequest(BaseModel):
    formation: str
    # Card Arena style; None keeps the current one.
    style: str | None = None
    # Legacy knobs (old clients); stored, no longer played.
    mentality: str = "BALANCED"
    playstyle: str = "CENTRAL_PLAY"


class PersonalSquadCoachRequest(BaseModel):
    user_coach_card_id: int | None = None


class PersonalSquadStadiumRequest(BaseModel):
    user_stadium_card_id: int | None = None


class PersonalSquadRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class PersonalSquadSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    user_card_id: int | None = None
    serial_number: int | None = None
    player: PlayerOut | None = None
    skill_code: str | None = None
    skill_level: int | None = None
    # The copy's own rating (stars, diamond, «Академия», artifacts, equipment
    # included), its line-fit in this slot (100 / 90 / 75 % —
    # lineup_service.slot_fit), the chemistry bonus (0 while chemistry is
    # off) and what that makes for the match: (rating + chemistry) × fit.
    rating: int | None = None
    fit_pct: int = 100
    chemistry_bonus: int = 0
    match_rating: int | None = None
    stars: int = 0
    path_stage: int = 0
    prestige: int = 0


class PersonalSquadOut(BaseModel):
    template_index: int
    name: str
    is_active: bool
    is_complete: bool
    formation: str
    mentality: str
    playstyle: str
    style: str = "possession"
    slots: list[PersonalSquadSlotOut]
    coach: EquippedCoachOut | None = None
    stadium: EquippedStadiumOut | None = None
    chemistry: ChemistryOut = ChemistryOut()
