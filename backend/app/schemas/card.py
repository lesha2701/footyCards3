from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import CardSource
from app.schemas.player import PlayerOut
from app.services.player_stats_service import effective_card_stats


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
    is_in_tactico_squad: bool
    hidden_from_trade: bool
    diamond_rating_bonus: int = 0

    @property
    def is_locked(self) -> bool:
        return self.is_locked_by_admin or self.is_locked_in_trade or self.is_in_lineup or self.is_in_tactico_squad

    @model_validator(mode="before")
    @classmethod
    def _apply_diamond_bonus(cls, data):
        """Bakes a diamond card's leveled-up rating/attack/defense into the
        nested `player` payload here, once, so every consumer that reads
        `card.player.rating` off this schema — collection, lineup slots,
        Tactico squad, gameplay strength calcs that read already-serialized
        data — sees the real per-copy value automatically, with no per-call-
        site changes needed. The underlying Player template is untouched."""
        if isinstance(data, dict):
            return data
        bonus = getattr(data, "diamond_rating_bonus", 0) or 0
        player_out = PlayerOut.model_validate(data.player)
        if bonus > 0:
            rating, attack, defense = effective_card_stats(data.player, bonus)
            player_out = player_out.model_copy(update={"rating": rating, "attack_rating": attack, "defense_rating": defense})
        return {
            "id": data.id,
            "serial_number": data.serial_number,
            "player": player_out,
            "acquired_at": data.acquired_at,
            "source": data.source,
            "is_locked_by_admin": data.is_locked_by_admin,
            "is_locked_in_trade": data.is_locked_in_trade,
            "is_in_lineup": data.is_in_lineup,
            "is_in_tactico_squad": data.is_in_tactico_squad,
            "hidden_from_trade": data.hidden_from_trade,
            "diamond_rating_bonus": bonus,
        }


class CollectionStatsOut(BaseModel):
    unique_players: int
    total_cards: int
    by_rarity: dict[str, int]
