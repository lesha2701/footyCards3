from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import CardSource
from app.schemas.player import PlayerOut
from app.services.player_stats_service import card_rating_bonus, effective_card_stats


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
    # The owner's own «замок»: no selling, no burning as material.
    is_user_locked: bool = False
    # Standing in a player-tournament squad (those don't set a flag on the
    # card); filled by the endpoints that list cards for picking.
    in_personal_squad: bool = False
    diamond_rating_bonus: int = 0
    # «Звёзды карточки» (services/card_star_service.py): earned stars, duplicates
    # banked toward the next one, and the rating the stars add (already baked
    # into player.rating below, like the diamond bonus).
    stars: int = 0
    star_progress: int = 0
    star_rating_bonus: int = 0
    # This copy's own skill (see services/card_skill_service.py); null = none.
    skill_code: Optional[str] = None
    skill_level: Optional[int] = None
    # «Академия» (services/path_service.py): levels gained, stage reached
    # (0 = Новичок …) and the rating they add (already in player.rating).
    path_level: int = 0
    path_stage: int = 0
    path_rating_bonus: int = 0
    # «Академия» prestige tier, its «Икона» number and the reforged talent.
    prestige: int = 0
    prestige_icon_number: Optional[int] = None
    talent_override: Optional[str] = None

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
        bonus = card_rating_bonus(data)
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
            "is_user_locked": bool(getattr(data, "is_user_locked", False)),
            "diamond_rating_bonus": getattr(data, "diamond_rating_bonus", 0) or 0,
            "stars": getattr(data, "stars", 0) or 0,
            "star_progress": getattr(data, "star_progress", 0) or 0,
            "star_rating_bonus": getattr(data, "star_rating_bonus", 0) or 0,
            "skill_code": getattr(data, "skill_code", None),
            "skill_level": getattr(data, "skill_level", None),
            "path_level": getattr(data, "path_level", 0) or 0,
            "path_stage": getattr(data, "path_stage", 0) or 0,
            "path_rating_bonus": getattr(data, "path_rating_bonus", 0) or 0,
            "prestige": getattr(data, "prestige", 0) or 0,
            "prestige_icon_number": getattr(data, "prestige_icon_number", None),
            "talent_override": getattr(data, "talent_override", None),
        }


class CollectionStatsOut(BaseModel):
    unique_players: int
    total_cards: int
    by_rarity: dict[str, int]
