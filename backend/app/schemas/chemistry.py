from typing import Optional

from pydantic import BaseModel


class ChemistryLinkOut(BaseModel):
    a: str
    b: str
    level: str  # "strong" | "medium" | "none"
    points: int


class PlayerChemistryOut(BaseModel):
    slot_code: str
    points: int
    link_sum: int
    on_position: bool
    rating_bonus: int
    # Extra points from «тренер-земляк» / «домашний стадион» (before the cap).
    coach_bonus: int = 0
    stadium_bonus: int = 0


class ChemistryRulesOut(BaseModel):
    link_strong: int
    link_medium: int
    thresholds: list[int]
    player_max: int
    player_floor: int
    rating_per_point: int
    off_position_penalty: int
    coach_country_points: int = 0
    stadium_club_points: int = 0


class ChemistryOut(BaseModel):
    """Neighbour-link chemistry of one lineup (services/chemistry_service.py).
    enabled=False: the mechanic is off, every other field but strength_bonus
    (the old flat club/country bonus) is empty — old clients ignore the
    whole object either way."""

    enabled: bool = False
    strength_bonus: Optional[int] = None
    # True when the rules come from a tournament that is already running
    # (frozen at its start), not from the live GameConfig — the editor then
    # says so; live_enabled is whether the mechanic is on in GameConfig now.
    frozen: bool = False
    live_enabled: bool = False
    formation: Optional[str] = None
    # Equipped coach's country / stadium's club the extras were computed with.
    coach_country: Optional[str] = None
    stadium_club: Optional[str] = None
    team: int = 0
    team_max: int = 0
    links: list[ChemistryLinkOut] = []
    players: list[PlayerChemistryOut] = []
    adjacency: list[list[str]] = []
    rules: Optional[ChemistryRulesOut] = None


class ChemistryPreviewSlotIn(BaseModel):
    slot_code: str
    user_card_id: int


class ChemistryPreviewRequest(BaseModel):
    formation: str = "4-3-3"
    slots: list[ChemistryPreviewSlotIn]
