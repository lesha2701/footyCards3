from typing import Optional

from pydantic import BaseModel, Field


class StarMaterialOut(BaseModel):
    id: int
    serial_number: int
    skill_code: Optional[str] = None
    skill_level: Optional[int] = None


class CardStarStateOut(BaseModel):
    """«Звёзды карточки» of one owned copy (services/card_star_service.py)."""

    card_id: int
    player_id: int
    rarity: str
    enabled: bool
    # Why this copy cannot take duplicates right now (null = it can).
    block_reason: Optional[str] = None
    stars: int
    max_stars: int
    progress: int
    # Duplicates needed for star 1..max and coins charged when each is claimed.
    thresholds: list[int]
    coin_costs: list[int]
    next_threshold: Optional[int] = None
    next_coin_cost: Optional[int] = None
    # Banked duplicates already cover the next star (claim needs only coins).
    claimable: bool = False
    dupes_to_max: int = 0
    rating_base: int
    rating_now: int
    rating_bonus: int
    rating_after_next_star: Optional[int] = None
    # Copies of the same player that can be fed in right now, skill-less first.
    free_duplicates: list[StarMaterialOut] = []


class CardStarFeedRequest(BaseModel):
    # Explicit copies to feed (in this order), or all_free=True to let the
    # server take every free skill-less duplicate of this player.
    material_card_ids: list[int] = Field(default_factory=list, max_length=200)
    all_free: bool = False
    confirm_skill_loss: bool = False
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class CardStarClaimRequest(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class CardStarOperationOut(BaseModel):
    kind: str  # feed | claim
    cards_consumed: int
    stars_gained: int
    coins_spent: int
    new_balance: int
    replayed: bool = False
    state: CardStarStateOut
