from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.coach import CoachBoostOut, CoachOut
from app.schemas.player import PlayerOut


class ClubCardAvailabilityOut(BaseModel):
    reason: str
    rounds_remaining: int


class ClubCardOut(BaseModel):
    id: int
    serial_number: int
    player: PlayerOut
    acquired_at: datetime
    is_in_lineup: bool
    availability: ClubCardAvailabilityOut | None = None


class EquippedCoachOut(BaseModel):
    """The coach currently equipped on a club's lineup — a leaner view than
    CoachOut (no admin-only fields like quick_sell_price/is_active/
    is_pack_droppable), used for ClubLineupOut.coach."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rarity: str
    image_path: str | None
    boosts: list[CoachBoostOut]


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
    template_index: int
    name: str
    is_active: bool
    is_complete: bool
    team_strength: int | None
    formation: str
    mentality: str
    playstyle: str
    tactical_fit: int
    tactical_fit_hint: str
    slots: list[ClubLineupSlotOut]
    coach: EquippedCoachOut | None = None
    training_uses_remaining: int = 0
    training_boost_active: bool = False
    in_active_tournament: bool = False
    # Same 4 rolled-up numbers NextOpponentOut shows for the opponent's
    # lineup, computed the same way (club_tactical_profile_service.compute_profile),
    # so the squad screen can show them for your own lineup too.
    attack: int = 0
    midfield: int = 0
    defence: int = 0
    goalkeeping: int = 0


class ClubLineupSlotIn(BaseModel):
    slot_code: str
    club_card_id: int


class ClubLineupSetRequest(BaseModel):
    slots: list[ClubLineupSlotIn]


class ClubCoachSetRequest(BaseModel):
    club_coach_card_id: int | None


class ClubTacticsSetRequest(BaseModel):
    formation: str
    mentality: str
    playstyle: str


class ClubLineupRenameRequest(BaseModel):
    name: str


class NextOpponentOut(BaseModel):
    round_number: int
    opponent_club_id: int
    opponent_club_name: str
    attack: int
    midfield: int
    defence: int
    goalkeeping: int
