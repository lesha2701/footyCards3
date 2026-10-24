from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class WeeklyTopAwardOut(BaseModel):
    id: int
    week_start: date
    metric: str
    metric_label: str
    rank: int
    value: int
    coins: int = 0
    pack_name: Optional[str] = None
    cards: int = 0
    cosmetic_name: Optional[str] = None
    cosmetic_style: Optional[str] = None
    # The player's balance now (the rewards are already in it) — the popup
    # updates the coin counter with it.
    balance: int = 0


class WeeklyTopSeenIn(BaseModel):
    ids: list[int]


class WeeklyTopPlaceOut(BaseModel):
    rank: int
    coins: int = 0
    pack_name: Optional[str] = None
    cosmetic_name: Optional[str] = None
    cosmetic_style: Optional[str] = None


class WeeklyTopInfoOut(BaseModel):
    enabled: bool
    size: int
    ends_at: datetime
    places: list[WeeklyTopPlaceOut]
    metrics: list[str]
    # Values a place must beat to count (ratings start above zero).
    starting_values: dict[str, int] = {}
