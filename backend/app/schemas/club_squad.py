from datetime import datetime

from pydantic import BaseModel

from app.schemas.coach import CoachOut
from app.schemas.player import PlayerOut


class ClubCardOut(BaseModel):
    id: int
    serial_number: int
    player: PlayerOut
    acquired_at: datetime
    is_in_lineup: bool


class ClubCoachCardOut(BaseModel):
    """One club-owned coach card — mirrors ClubCardOut above field-for-field,
    substituting `coach: CoachOut` for the player field. Added as part of
    Task 3 (club coach pack purchase/opening) rather than Task 5, since
    Task 3's router needs it first chronologically — see this plan's Task 3
    brief note on schema ordering."""

    id: int
    serial_number: int
    coach: CoachOut
    acquired_at: datetime


class ClubLineupSlotOut(BaseModel):
    slot_code: str
    category: str
    ideal_position: str
    card: ClubCardOut | None = None


class ClubLineupOut(BaseModel):
    is_complete: bool
    team_strength: int | None
    formation: str
    mentality: str
    playstyle: str
    tactical_fit: int
    tactical_fit_hint: str
    slots: list[ClubLineupSlotOut]


class ClubLineupSlotIn(BaseModel):
    slot_code: str
    club_card_id: int


class ClubLineupSetRequest(BaseModel):
    slots: list[ClubLineupSlotIn]


class ClubTacticsSetRequest(BaseModel):
    formation: str
    mentality: str
    playstyle: str


class NextOpponentOut(BaseModel):
    round_number: int
    opponent_club_id: int
    opponent_club_name: str
    attack: int
    midfield: int
    defence: int
    goalkeeping: int
