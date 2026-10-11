from typing import Optional

from pydantic import BaseModel, Field


class MyPlayerCreateIn(BaseModel):
    name: str = Field(max_length=40)
    number: int = 10
    position: str
    appearance: dict[str, int] = Field(default_factory=dict)


class MyPlayerUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=40)
    number: Optional[int] = None
    position: Optional[str] = None
    appearance: Optional[dict[str, int]] = None


class MyPlayerTrainIn(BaseModel):
    attr: str
    points: int = Field(default=1, ge=1, le=100)


class MyPlayerSkillIn(BaseModel):
    code: str


class MyPlayerStarsInvoiceIn(BaseModel):
    # "training" (one extra training) | "item" (an «Имущество» item).
    purchase: str
    item_id: Optional[int] = None


class MyPlayerStarsInvoiceOut(BaseModel):
    invoice_link: str
    payload_token: str
    stars_amount: int


class MyPlayerTrainingFinishIn(BaseModel):
    hits: int = Field(ge=0, le=3)


class MyPlayerCosmeticBuyIn(BaseModel):
    code: str


class MyPlayerCosmeticEquipIn(BaseModel):
    kind: str
    code: Optional[str] = None


class MyPlayerOut(BaseModel):
    name: str
    number: int
    position: str
    category: str
    appearance: dict[str, int]
    attributes: dict[str, int]
    rating: int
    attack_rating: int
    defense_rating: int
    tier: str
    tier_label: str
    # The attribute that matters most at this position: atk | def.
    key_attr: str
    accessory: Optional[str] = None
    background: Optional[str] = None


class MyPlayerViewOut(BaseModel):
    enabled: bool
    # The player's coin balance (to refresh the top bar after a purchase).
    balance: int = 0
    player: Optional[MyPlayerOut] = None
    xp: int
    level: int
    xp_into_level: int
    xp_for_next: int
    xp_today: int
    xp_daily_cap: int
    xp_per_reward: int
    xp_career_match: int
    points_available: int
    points_per_level: int
    rating_cap: int
    at_rating_cap: bool
    tier_thresholds: list[int]
    appearance_options: dict[str, int]
    attr_labels: dict[str, str]
    next_tier_at: Optional[int] = None
    skill: Optional["MyPlayerSkillOut"] = None
    training: "MyPlayerTrainingOut"
    cosmetics: "MyPlayerCosmeticsOut"
    # Only on the training-finish response: XP credited by that run.
    training_xp: Optional[int] = None


class MyPlayerPublicOut(BaseModel):
    player: Optional[MyPlayerOut] = None
    level: Optional[int] = None


class MyPlayerSkillOptionOut(BaseModel):
    code: str
    name: str
    icon: str
    effect: str
    bonus_phrase: str = ""


class MyPlayerSkillUpgradeOut(BaseModel):
    to_level: int
    token_cost: int
    coin_cost: int


class MyPlayerSkillOut(BaseModel):
    # card_skills_enabled (the whole card-skill mechanic).
    enabled: bool
    code: Optional[str] = None
    name: Optional[str] = None
    icon: Optional[str] = None
    # 0 = no skill yet.
    level: int
    level_label: Optional[str] = None
    upgrade: Optional[MyPlayerSkillUpgradeOut] = None
    # Card-skill prices (GameConfig.card_skill_*).
    assign_token_cost: int
    assign_coin_cost: int
    replace_token_cost: int
    replace_coin_cost: int
    # Skill-token balance by skill code.
    tokens: dict[str, int]
    options: list[MyPlayerSkillOptionOut]


class MyPlayerTrainingOut(BaseModel):
    # The free daily run is used up.
    done_today: bool
    # A run can start now (free one left, or a bought credit).
    can_train: bool
    extra_credits: int
    extra_bought_today: int
    extra_max: int
    extra_left_today: int
    extra_coins_price: int
    extra_stars_price: int
    xp_base: int
    xp_per_hit: int
    max_hits: int


class MyPlayerTrainingStartOut(BaseModel):
    max_hits: int
    min_seconds: int


class MyPlayerCosmeticItemOut(BaseModel):
    code: str
    kind: str
    name: str
    price: int
    owned: bool


class MyPlayerCosmeticsOut(BaseModel):
    owned: list[str]
    accessory: Optional[str] = None
    background: Optional[str] = None
    catalog: list[MyPlayerCosmeticItemOut]


class MyPlayerLeaderboardEntryOut(BaseModel):
    rank: int
    user_id: int
    is_me: bool
    user_name: str
    level: int
    player: MyPlayerOut


class MyPlayerLeaderboardOut(BaseModel):
    scope: str
    entries: list[MyPlayerLeaderboardEntryOut]
    me: Optional[MyPlayerLeaderboardEntryOut] = None


MyPlayerViewOut.model_rebuild()


class LifestyleItemOut(BaseModel):
    id: int
    name: str
    description: str
    category: str
    emoji: str
    image_path: Optional[str] = None
    coins_price: int
    stars_price: int
    prestige: int
    max_supply: Optional[int] = None
    sold_count: int
    sold_out: bool
    owned: bool
    serial_number: Optional[int] = None


class LifestyleCategoryOut(BaseModel):
    code: str
    label: str


class LifestyleCatalogOut(BaseModel):
    categories: list[LifestyleCategoryOut]
    items: list[LifestyleItemOut]
    prestige: int
    balance: int = 0


class LifestylePublicOut(BaseModel):
    items: list[LifestyleItemOut]
    prestige: int


class AdminLifestyleItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    category: str = "other"
    emoji: str = Field(default="⭐", max_length=16)
    coins_price: int = Field(default=0, ge=0)
    stars_price: int = Field(default=0, ge=0, le=100000)
    prestige: int = Field(default=10, ge=0, le=100000)
    max_supply: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True
    sort_order: int = 0


class AdminLifestyleItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = None
    emoji: Optional[str] = Field(default=None, max_length=16)
    coins_price: Optional[int] = Field(default=None, ge=0)
    stars_price: Optional[int] = Field(default=None, ge=0, le=100000)
    prestige: Optional[int] = Field(default=None, ge=0, le=100000)
    # Explicit null = unlimited.
    max_supply: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class AdminLifestyleItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str
    category: str
    emoji: str
    image_path: Optional[str] = None
    coins_price: int
    stars_price: int
    prestige: int
    max_supply: Optional[int] = None
    sold_count: int
    is_active: bool
    sort_order: int
