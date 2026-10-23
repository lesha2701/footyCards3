from typing import Optional

from pydantic import BaseModel, Field


class MyPlayerCreateIn(BaseModel):
    name: str = Field(max_length=40)
    number: int = 10
    position: str
    appearance: dict[str, int] = Field(default_factory=dict)
    # National team (one of the view's `countries`).
    country: Optional[str] = Field(default=None, max_length=64)


class MyPlayerUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=40)
    number: Optional[int] = None
    position: Optional[str] = None
    appearance: Optional[dict[str, int]] = None
    # Explicit null clears it.
    country: Optional[str] = Field(default=None, max_length=64)


class MyPlayerTrainIn(BaseModel):
    attr: str
    points: int = Field(default=1, ge=1, le=100)


class MyPlayerSkillIn(BaseModel):
    code: str


class MyPlayerStarsInvoiceIn(BaseModel):
    # "training" (one extra training) | "item" (an «Имущество» item, item_id)
    # | "cosmetic" (code) | "role" (line change to `position`) | "career"
    # (code = pro | agent | refresh | heal | save_offer | fast; `position`
    # carries the club key for save_offer) | "manager" (code = pro | a club
    # style item of GameConfig.manager_cosmetics).
    purchase: str
    item_id: Optional[int] = None
    code: Optional[str] = Field(default=None, max_length=32)
    position: Optional[str] = Field(default=None, max_length=96)


class MyPlayerRoleIn(BaseModel):
    position: str = Field(max_length=8)


class MyPlayerDuelIn(BaseModel):
    opponent_user_id: int


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
    effect: Optional[str] = None
    celebration: Optional[str] = None
    country: Optional[str] = None
    # «Карьера Pro» is active.
    pro: bool = False


class MyPlayerLevelUpOut(BaseModel):
    from_level: int
    to_level: int
    # Attribute points the new levels brought.
    points: int


class MyPlayerFreshnessOut(BaseModel):
    value: int
    # Rating points the player loses in matches right now.
    penalty: int
    max_penalty: int
    regen_per_hour: int
    # Part of regen_per_hour that comes from «Имущество».
    regen_bonus: int = 0
    per_match: int
    training: int


class MyPlayerRoleChangeOut(BaseModel):
    coins_price: int
    stars_price: int


class MyPlayerTrophyOut(BaseModel):
    id: int
    code: str
    name: str
    icon: str
    image_path: Optional[str] = None
    message: Optional[str] = None
    granted_at: str


class MyPlayerAttentionOut(BaseModel):
    """What the top-bar dot is for (any true = show it)."""
    create: bool = False
    level_up: bool = False
    points: bool = False
    training: bool = False
    income: bool = False
    career_offers: bool = False


class MyPlayerStreakRewardOut(BaseModel):
    tokens: int
    skill_code: str
    skill_name: str
    skill_icon: str
    streak: int


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
    xp_stratego_match: int = 0
    xp_player_career_match: int = 0
    # XP bonus from «Имущество», percent.
    xp_bonus_pct: int = 0
    points_available: int
    points_per_level: int
    level_seen: int = 1
    # Set while the level-up screen hasn't been shown for the current level.
    level_up: Optional[MyPlayerLevelUpOut] = None
    rating_cap: int
    at_rating_cap: bool
    tier_thresholds: list[int]
    appearance_options: dict[str, int]
    attr_labels: dict[str, str]
    next_tier_at: Optional[int] = None
    skill: Optional["MyPlayerSkillOut"] = None
    training: "MyPlayerTrainingOut"
    cosmetics: "MyPlayerCosmeticsOut"
    freshness: Optional[MyPlayerFreshnessOut] = None
    role_change: Optional[MyPlayerRoleChangeOut] = None
    trophies: list[MyPlayerTrophyOut] = []
    attention: MyPlayerAttentionOut = MyPlayerAttentionOut()
    # Countries the player can represent (national team).
    countries: list[str] = []
    # Only on the training-finish response: XP credited by that run, and
    # the skill tokens a streak paid (if this run completed one).
    training_xp: Optional[int] = None
    streak_reward: Optional[MyPlayerStreakRewardOut] = None


class MyPlayerPublicOut(BaseModel):
    player: Optional[MyPlayerOut] = None
    level: Optional[int] = None
    trophies: list[MyPlayerTrophyOut] = []


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


class MyPlayerDrillOut(BaseModel):
    # shot | pass | tackle | save
    code: str
    name: str
    hint: str


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
    # Today's drill (follows the weekday and the line).
    drill: MyPlayerDrillOut
    # Free trainings in a row; every streak_days pays streak_tokens skill tokens.
    streak: int = 0
    streak_days: int = 7
    streak_tokens: int = 1
    streak_left: int = 7
    # Freshness one training restores.
    freshness_bonus: int = 0


class MyPlayerTrainingStartOut(BaseModel):
    max_hits: int
    min_seconds: int
    drill: str = "shot"


class MyPlayerCosmeticItemOut(BaseModel):
    code: str
    # accessory | background | effect | hair
    kind: str
    name: str
    # Coins / Telegram Stars; 0 = not sold for that currency.
    price: int
    stars_price: int = 0
    owned: bool
    # «Статус» it adds; premium hairstyle → the appearance hair index it sets.
    status: int = 0
    hair_index: Optional[int] = None


class MyPlayerCosmeticsOut(BaseModel):
    owned: list[str]
    accessory: Optional[str] = None
    background: Optional[str] = None
    effect: Optional[str] = None
    hair: Optional[str] = None
    celebration: Optional[str] = None
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


class MyPlayerDuelFriendOut(BaseModel):
    user_id: int
    user_name: str
    level: int
    player: MyPlayerOut


class MyPlayerDuelEventOut(BaseModel):
    n: int
    # me | opp — from the viewer's side.
    side: str
    # goal | save | miss
    outcome: str


class MyPlayerDuelSideOut(MyPlayerOut):
    # Rating as fielded in the duel (fatigue included).
    match_rating: Optional[int] = None


class MyPlayerDuelOut(BaseModel):
    id: int
    created_at: str
    # The viewer started it (only the challenger is rewarded).
    as_challenger: bool
    opponent_user_id: int
    opponent_name: str
    my_goals: int
    opp_goals: int
    # win | draw | loss — from the viewer's side.
    result: str
    reward_coins: int
    events: list[MyPlayerDuelEventOut]
    me: Optional[MyPlayerDuelSideOut] = None
    opp: Optional[MyPlayerDuelSideOut] = None


class MyPlayerDuelsOut(BaseModel):
    enabled: bool
    left_today: int
    per_day: int
    reward_win: int
    reward_draw: int
    xp: int
    attacks: int
    friends: list[MyPlayerDuelFriendOut]
    recent: list[MyPlayerDuelOut]


class MyPlayerDuelPlayOut(BaseModel):
    duel: MyPlayerDuelOut
    duels: MyPlayerDuelsOut
    balance: int


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
    # none | freshness_regen | xp_bonus_pct | weekly_income
    effect: str = "none"
    effect_value: int = 0
    effect_label: str = ""
    # weekly_income: coins ready to claim on this item, and when the next week completes.
    income_ready: int = 0
    next_income_at: Optional[str] = None


class LifestyleCategoryOut(BaseModel):
    code: str
    label: str


class LifestyleEffectTotalOut(BaseModel):
    effect: str
    value: int
    label: str


class LifestyleCatalogOut(BaseModel):
    categories: list[LifestyleCategoryOut]
    items: list[LifestyleItemOut]
    prestige: int
    balance: int = 0
    # Effects summed over everything owned.
    effects: list[LifestyleEffectTotalOut] = []
    income_ready: int = 0
    # Only on the claim response: coins just credited.
    claimed: Optional[int] = None


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
    effect: str = "none"
    effect_value: int = Field(default=0, ge=0, le=100000)


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
    effect: Optional[str] = None
    effect_value: Optional[int] = Field(default=None, ge=0, le=100000)


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
    effect: str = "none"
    effect_value: int = 0
