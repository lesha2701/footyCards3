from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import CardSource
from app.schemas.player import PlayerOut


class UserCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    serial_number: int
    player: PlayerOut
    acquired_at: datetime
    source: CardSource
    is_locked_by_admin: bool
    is_locked_in_trade: bool
    is_in_lineup: bool
    hidden_from_trade: bool

    @property
    def is_locked(self) -> bool:
        return self.is_locked_by_admin or self.is_locked_in_trade or self.is_in_lineup


class CollectionStatsOut(BaseModel):
    unique_players: int
    total_cards: int
    by_rarity: dict[str, int]
