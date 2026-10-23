from datetime import datetime
from typing import List, Literal, Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import CardSource, Position, Rarity
from app.schemas.player import PlayerOut
from app.services.player_stats_service import card_rating_bonus, effective_card_stats


class UserCardListItem(BaseModel):
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
    duplicate_count: int = 1
    diamond_rating_bonus: int = 0
    # «Звёзды карточки» (services/card_star_service.py): earned stars, duplicates
    # banked toward the next one, and the rating the stars add (already baked
    # into player.rating below, like the diamond bonus).
    stars: int = 0
    star_progress: int = 0
    star_rating_bonus: int = 0
    # This copy's own skill (null = none).
    skill_code: Optional[str] = None
    skill_level: Optional[int] = None
    # «Академия» (services/path_service.py): levels gained, stage reached
    # (0 = Новичок …) and the rating they add (already in player.rating).
    path_level: int = 0
    path_stage: int = 0
    path_rating_bonus: int = 0
    # «Экипировка» it wears (services/equipment_service.py; rating already in player.rating).
    equipment_rating_bonus: int = 0
    equipment_chemistry: int = 0
    equipment_boosts: Optional[dict] = None
    # «Академия» prestige tier, its «Икона» number and the reforged talent.
    prestige: int = 0
    prestige_icon_number: Optional[int] = None
    talent_override: Optional[str] = None
    # Every skilled copy of this player the owner has — the list collapses
    # duplicates into one representative, so the album badge needs these.
    skilled_copies: List["SkilledCopyOut"] = []

    @model_validator(mode="before")
    @classmethod
    def _apply_diamond_bonus(cls, data):
        """Same per-copy rating bake-in as UserCardOut — see its docstring."""
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
            "equipment_rating_bonus": getattr(data, "equipment_rating_bonus", 0) or 0,
            "equipment_chemistry": getattr(data, "equipment_chemistry", 0) or 0,
            "equipment_boosts": getattr(data, "equipment_boosts", None) or None,
            "prestige": getattr(data, "prestige", 0) or 0,
            "prestige_icon_number": getattr(data, "prestige_icon_number", None),
            "talent_override": getattr(data, "talent_override", None),
        }


class SkilledCopyOut(BaseModel):
    id: int
    serial_number: int
    skill_code: str
    skill_level: int


UserCardListItem.model_rebuild()


SortBy = Literal["rating", "rarity", "acquired_at"]
SortDir = Literal["asc", "desc"]


class CollectionFilterParams:
    def __init__(
        self,
        rarity: Optional[List[Rarity]] = Query(None),
        country: Optional[str] = None,
        club: Optional[str] = None,
        position: Optional[Position] = None,
        min_rating: Optional[int] = None,
        max_rating: Optional[int] = None,
        collection_id: Optional[int] = None,
        search: Optional[str] = None,
        sort_by: SortBy = "acquired_at",
        sort_dir: SortDir = "desc",
        has_skill: Optional[bool] = None,
    ):
        self.rarity = rarity
        self.country = country
        self.club = club
        self.position = position
        self.min_rating = min_rating
        self.max_rating = max_rating
        self.collection_id = collection_id
        self.search = search
        self.sort_by = sort_by
        self.sort_dir = sort_dir
        # True = only copies with a skill, False = only copies without one.
        self.has_skill = has_skill


class SetCardHiddenRequest(BaseModel):
    hidden: bool


class SetCardsLockedRequest(BaseModel):
    """The owner's «замок» on one or several copies."""
    card_ids: List[int]
    locked: bool


class SetCardsLockedOut(BaseModel):
    card_ids: List[int]
    locked: bool


class CardFilterOptionsOut(BaseModel):
    countries: List[str]
    clubs: List[str]


class CardFilterDefault(BaseModel):
    """Saved default card filter; every field optional (unset = any)."""
    rarity: Optional[str] = None
    country: Optional[str] = None
    club: Optional[str] = None
    position: Optional[str] = None
    sort_by: Optional[str] = None
    has_skill: Optional[bool] = None


class SellCardRequest(BaseModel):
    user_card_id: int
    confirm_last_copy: bool = False
    # Must be true to sell a copy that has a skill (lost without token refund).
    confirm_skill_loss: bool = False


class BulkSellRequest(BaseModel):
    user_card_ids: List[int]
    confirm_last_copy: bool = False
    # Must be true to sell a copy that has a skill (lost without token refund).
    confirm_skill_loss: bool = False


class SellResultOut(BaseModel):
    sold_count: int
    coins_earned: int
    new_balance: int


class SellDuplicatesRequest(BaseModel):
    # true = only count what would be sold (for the confirmation dialog).
    preview: bool = True
    include_diamond: bool = False
    # Also sell the spares of players whose copy already has stars or a
    # started «копилка» (off by default: they are star material).
    include_star_material: bool = False


class SellDuplicatesOut(SellResultOut):
    by_rarity: dict[str, int] = {}
    preview: bool


class AlbumCollectionSummaryOut(BaseModel):
    id: int  # -1 for the synthetic "Other players" bucket
    name: str
    description: str
    image_path: Optional[str]
    owned_count: int
    total_count: int
    is_complete: bool
    reward_coins: int
    reward_pack_name: Optional[str]
    reward_claimed: bool


class AlbumOverviewOut(BaseModel):
    collections: List[AlbumCollectionSummaryOut]
    overall_owned: int
    overall_total: int


class AlbumPlayerOut(BaseModel):
    player: PlayerOut
    owned: bool
    duplicate_count: int
    card: Optional[UserCardListItem] = None


class AlbumCollectionDetailOut(BaseModel):
    id: int
    name: str
    description: str
    image_path: Optional[str]
    reward_coins: int
    reward_pack_name: Optional[str]
    owned_count: int
    total_count: int
    is_complete: bool
    reward_claimed: bool
    players: List[AlbumPlayerOut]
