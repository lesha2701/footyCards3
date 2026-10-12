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


class ChemistryRulesOut(BaseModel):
    link_strong: int
    link_medium: int
    thresholds: list[int]
    player_max: int
    player_floor: int
    rating_per_point: int
    off_position_penalty: int


class ChemistryOut(BaseModel):
    """Neighbour-link chemistry of one lineup (services/chemistry_service.py).
    enabled=False: the mechanic is off, every other field but strength_bonus
    (the old flat club/country bonus) is empty — old clients ignore the
    whole object either way."""

    enabled: bool = False
    strength_bonus: Optional[int] = None
    formation: Optional[str] = None
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
