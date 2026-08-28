import enum
from typing import Optional

from pydantic import BaseModel

from app.models.enums import ClubLogoShape


class ClubRankingMetric(str, enum.Enum):
    cups = "cups"
    stars = "stars"


class ClubRankingEntry(BaseModel):
    rank: int
    club_id: int
    name: str
    logo_shape: ClubLogoShape
    logo_color: str
    value: int


class ClubRankingOut(BaseModel):
    metric: ClubRankingMetric
    top: list[ClubRankingEntry]
    me: Optional[ClubRankingEntry] = None
