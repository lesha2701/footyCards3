from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.enums import Position

SkillOperation = Literal["assign", "upgrade", "replace"]


class SkillLevelEffectOut(BaseModel):
    level: int
    level_label: str
    bonus_pp: int


class SkillCatalogItemOut(BaseModel):
    code: str
    name: str
    icon: str
    effect: str
    applies_in: list[str]
    not_affected: str
    positions: list[Position]
    max_positions: list[Position]
    levels: list[SkillLevelEffectOut]
    engine_supported: bool
    is_enabled: bool
    # True only when a NEW skill of this kind can be obtained right now
    # (mechanic on + engine supports it + admin has it enabled).
    is_available: bool
    unavailable_reason: Optional[str] = None
    remaining_work: list[str] = []
    sort_order: int = 0


class SkillCostOut(BaseModel):
    token_cost: int
    coin_cost: int


class SkillCostsOut(BaseModel):
    assign: SkillCostOut
    upgrade_to_2: SkillCostOut
    upgrade_to_3: SkillCostOut
    replace: SkillCostOut


class SkillRulesOut(BaseModel):
    enabled: bool
    max_level: int
    event_bonus_cap_pp: int
    probability_floor_pct: int
    probability_ceiling_pct: int
    costs: SkillCostsOut


class SkillCatalogOut(BaseModel):
    rules: SkillRulesOut
    skills: list[SkillCatalogItemOut]


class SkillTokenBalanceOut(BaseModel):
    skill_code: str
    quantity: int


class SkillTokensOut(BaseModel):
    tokens: list[SkillTokenBalanceOut]


class CardSkillOut(BaseModel):
    code: str
    level: int
    level_label: str
    bonus_pp: int
    # False when the card's position no longer fits the server catalog (e.g.
    # an admin edited the player's position) — the skill is kept but has no
    # match effect until replaced.
    is_effective: bool


class SkillActionOut(BaseModel):
    operation: SkillOperation
    skill_code: str
    target_level: int
    token_cost: int
    coin_cost: int
    tokens_owned: int
    allowed: bool
    reason: Optional[str] = None


class CardCopyOut(BaseModel):
    id: int
    serial_number: int
    skill_code: Optional[str] = None
    skill_level: Optional[int] = None
    is_locked_in_trade: bool
    is_in_lineup: bool
    is_in_tactico_squad: bool
    is_locked_by_admin: bool


class CardSkillStateOut(BaseModel):
    card_id: int
    serial_number: int
    player_id: int
    player_name: str
    position: Position
    skill: Optional[CardSkillOut] = None
    next_level_bonus_pp: Optional[int] = None
    # Card-wide blocker (in a trade, admin-locked, mechanic off) — when set,
    # every action below is disallowed for this reason.
    blocked_reason: Optional[str] = None
    actions: list[SkillActionOut]
    copies: list[CardCopyOut]


class SkillOperationRequest(BaseModel):
    operation: SkillOperation
    # Required for assign/replace (the new skill); ignored for upgrade.
    skill_code: Optional[str] = None
    # The state the player confirmed in the UI. A mismatch with the card's
    # current state is rejected instead of silently charging for a different
    # change.
    expected_skill_code: Optional[str] = None
    expected_level: Optional[int] = Field(default=None, ge=1, le=3)
    expected_token_cost: int = Field(ge=0)
    expected_coin_cost: int = Field(ge=0)
    # Same convention as pack opening: a client-generated key per confirmed
    # action; a retry with the same key replays instead of charging again.
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class SkillOperationOut(BaseModel):
    operation: SkillOperation
    card_id: int
    skill_code: str
    skill_level: int
    previous_skill_code: Optional[str] = None
    previous_level: Optional[int] = None
    token_cost: int
    coin_cost: int
    tokens_left: int
    new_balance: int
    replayed: bool = False


class AdminSkillUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    # Subset of the server catalog's positions; [] is rejected, null resets to all.
    allowed_positions: Optional[list[Position]] = None
    reset_positions: bool = False
    sort_order: Optional[int] = None


class AdminTokenGrantRequest(BaseModel):
    user_id: int
    skill_code: str
    # Negative = correction (cannot take the balance below zero).
    quantity: int = Field(ge=-1000, le=1000)
    reason: str = Field(min_length=1, max_length=255)
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class AdminUserTokensOut(BaseModel):
    user_id: int
    tokens: list[SkillTokenBalanceOut]


class SkillLedgerEntryOut(BaseModel):
    id: int
    user_id: int
    kind: str
    skill_code: str
    token_delta: int
    token_balance_after: int
    coins_spent: int
    user_card_id: Optional[int] = None
    from_skill_code: Optional[str] = None
    from_level: Optional[int] = None
    to_skill_code: Optional[str] = None
    to_level: Optional[int] = None
    admin_id: Optional[int] = None
    related_object_type: Optional[str] = None
    related_object_id: Optional[int] = None
    reason: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
