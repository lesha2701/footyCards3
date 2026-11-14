from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.ranking import RankingEntry

Faction = Literal["dawn", "ash"]
Difficulty = Literal["easy", "normal", "hard"]


class MagicUnitOut(BaseModel):
    code: str
    name: str
    tier: int
    emoji: str
    ranged: bool
    flying: bool
    ability_text: str
    hp: int
    atk: int
    defence: int
    dmin: int
    dmax: int
    spd: int
    # A position variant: who becomes this creature ("нападающие", …); "" — the base one.
    note: str = ""


class MagicSpellOut(BaseModel):
    code: str
    name: str
    cost: int
    target: str
    description: str
    level: int = 1  # hero level that unlocks it


class MagicFactionOut(BaseModel):
    code: str
    name: str
    emoji: str
    tagline: str
    units: list[MagicUnitOut]
    spells: list[MagicSpellOut]


class MagicDifficultyOut(BaseModel):
    code: str
    label: str
    reward_pct: int
    pack_chance_pct: int
    rating_win: int


class MagicModeOut(BaseModel):
    code: str
    label: str
    days: int
    cells: int
    reward_pct: int
    pack_chance_pct: int
    runs: int = 1  # every mode has its own runs of the day; a run is one of them
    moves: int = 9  # the hero's moves a day (before the class bonus)
    # This mode's runs today: free left of free_total, bought ones waiting (bank), the next
    # one's price for coins (the day's first) or for Stars (stars_left more), None — not sold.
    free_total: int = 0
    free_left: int = 0
    bank: int = 0
    price_coins: Optional[int] = None
    price_stars: Optional[int] = None
    stars_left: int = 0


class MagicChallengeRowOut(BaseModel):
    rank: int
    name: str
    score: int
    me: bool = False


class MagicChallengeOut(BaseModel):
    week: str
    ends_at: datetime
    best: Optional[int] = None  # my best score this week
    plays: int = 0
    top: list[MagicChallengeRowOut] = []


class MagicCardOut(BaseModel):
    player_id: int
    name: str
    image_path: Optional[str] = None
    rarity: str
    rating: int
    position: str
    club: Optional[str] = None


class MagicCreatureOut(BaseModel):
    unit: str
    faction: str
    name: str
    emoji: str
    tier: int
    fighters: int  # what the collection holds (cards × fighters per card, less the fallen)


class MagicCreaturePackOut(BaseModel):
    size: int
    coins: Optional[int] = None
    stars: Optional[int] = None
    odds: dict[int, float]  # tier → %
    fighters: dict[int, int]  # tier → fighters per card


class MagicWoundedOut(BaseModel):
    unit: str
    name: str
    emoji: str
    tier: int
    count: int
    until: datetime


class MagicCasualtyOut(BaseModel):
    unit: str
    name: str
    emoji: str
    tier: int
    count: int


class MagicReviveOut(BaseModel):
    dead: list["MagicCasualtyOut"] = []
    essence: int = 0  # taken back (the essence those dead gave)


class MagicCasualtiesOut(BaseModel):
    guard_lost: int = 0
    captains_xp: int = 0
    dead: list[MagicCasualtyOut] = []
    wounded: list[MagicCasualtyOut] = []
    essence: int = 0
    until: Optional[datetime] = None  # when the wounded are back
    won_faster: bool = False


class MagicRiskOut(BaseModel):
    """What a run may cost the collection — shown before every start."""
    dead_pct: dict[str, int]  # by mode: of the fallen, this % dies for good
    wounded_hours: int
    wounded_hours_win: int
    essence_per_fighter: dict[int, int]
    hardcore_essence_x: int = 2


class MagicHealOut(BaseModel):
    healed: int
    essence: int
    creatures: list["MagicCreatureOut"]


class MagicShopItemOut(BaseModel):
    code: str  # "pack" | "leadership" | "mana" | "skin:<cosmetic id>"
    kind: str  # "pack" | "leadership" | "mana" | "skin"
    title: str
    text: str
    price: int  # essence
    owned: int = 0  # leadership / mana bought so far
    max: Optional[int] = None
    available: bool = True  # false: at the cap / already owned
    skin_kind: Optional[str] = None  # magic_hero / magic_castle
    style_key: Optional[str] = None


class MagicShopOut(BaseModel):
    essence: int
    items: list[MagicShopItemOut]


class MagicShopBuyOut(BaseModel):
    essence: int
    item: str
    cards: list["MagicCreatureOut"] = []  # a pack


class MagicShopBuyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class MagicPackOpenOut(BaseModel):
    cards: list[MagicCreatureOut]  # one per card, fighters = that card's
    creatures: list[MagicCreatureOut]
    balance: int


class MagicArmyStackOut(BaseModel):
    """A stack of the army: a creature of the collection, led by a footballer captain (optional)."""
    unit: str
    name: str
    emoji: str
    faction: str
    tier: int
    have: int  # fighters of this creature in the collection
    count: int  # fighters that march (have, up to the cap; halved when unruly)
    cost: int  # leadership
    unruly: bool = False  # over the leadership budget: fights at half strength
    power: int
    captain: Optional[MagicCardOut] = None
    captain_level: int = 1
    captain_traits: list[str] = []


class MagicTraitOut(BaseModel):
    code: str
    emoji: str
    name: str
    text: str


class MagicCaptainOut(BaseModel):
    card: MagicCardOut
    cap: int  # the highest creature tier this footballer may lead
    copies: int
    level: int = 1
    xp: int = 0
    next_xp: Optional[int] = None  # XP of the next level; None at the top
    traits: list[str] = []
    trait_slots: int = 0  # traits it may hold at this level
    spare: int = 0  # copies that may be fed to it (+XP) — every copy but one
    dup_xp: int = 0  # XP one fed copy gives
    fed_left: int = 0  # copies it may still eat today


class MagicGuardMaterialOut(BaseModel):
    card: MagicCardOut
    spare: int
    points: int  # per copy (6 = one fighter)


class MagicGuardOut(BaseModel):
    card: Optional[MagicCardOut] = None
    level: int = 1
    xp: int = 0
    next_xp: Optional[int] = None
    count: int = 0
    size: int  # the most fighters at this level
    points: int = 0  # toward the next fighter (of `fighter_points`)
    fighter_points: int = 6
    unit: Optional[str] = None  # the guard's creature (by the footballer's rarity)
    tier: int = 3
    ability: Optional[str] = None
    traits: list[str] = []
    trait_slots: int = 0
    materials: list[MagicGuardMaterialOut] = []


class MagicArmyOut(BaseModel):
    stacks: list[MagicArmyStackOut]
    creatures: list[MagicCreatureOut]
    captains: list[MagicCaptainOut]
    max_stacks: int
    stack_cap: int
    auto: bool
    hero_class: str = "knight"
    leadership: int
    leadership_used: int
    costs: dict[int, int]
    guard: Optional[MagicGuardOut] = None
    traits: list[MagicTraitOut] = []
    captain_xp: list[int] = []
    guard_xp: list[int] = []


class MagicArmyPick(BaseModel):
    unit: str
    captain: Optional[int] = None


class MagicArmySetRequest(BaseModel):
    stacks: list[MagicArmyPick] = Field(min_length=1, max_length=5)


class MagicHeroClassOut(BaseModel):
    code: str
    name: str
    emoji: str
    tagline: str
    mana: int
    spell_power: int
    moves: int


class MagicHeroOut(BaseModel):
    level: int
    xp: int
    level_start: int
    next_level_xp: Optional[int] = None
    mana: int
    spell_power: int


class MagicHubOut(BaseModel):
    enabled: bool
    hero: MagicHeroOut
    rating: int
    rank: Optional[int] = None
    wins: int
    active_run_id: Optional[int] = None
    rewarded_today: int
    daily_limit: int
    # Runs: free ones left today, bought ones banked, the next extra's price.
    free_left: int = 0
    bonus_runs: int = 0
    extra_runs_today: int = 0
    extra_runs_limit: int = 0
    extra_price_coins: Optional[int] = None
    extra_price_stars: Optional[int] = None
    can_start: bool = True
    challenge_left: int = 0  # the weekly challenge: tries left today
    retry_coins: int = 0
    retry_stars: int = 0
    retries_left: int = 0
    retry_credits: int = 0
    gold_coins_pct: int = 0
    hero_skin: str = "default"
    castle_skin: str = "default"
    reward_win: int
    reward_loss: int
    pack_name: Optional[str] = None
    days: int
    moves_per_day: int
    factions: list[MagicFactionOut]
    hero_classes: list[MagicHeroClassOut] = []
    creatures: list[MagicCreatureOut] = []
    creature_pack: Optional[MagicCreaturePackOut] = None
    last_pack: list[MagicCreatureOut] = []
    essence: int = 0
    wounded: list[MagicWoundedOut] = []
    heal_essence: int = 0  # the essence price to heal every wounded now
    heal_stars: Optional[int] = None
    risk: Optional[MagicRiskOut] = None
    refill_today: bool = False  # the free starter set came back today (the collection was empty)
    revive: Optional[MagicReviveOut] = None  # the one free revival, while it's on offer
    guard: Optional["MagicGuardOut"] = None
    skin_classes: dict[str, str] = {}
    difficulties: list[MagicDifficultyOut]
    modes: list[MagicModeOut] = []
    challenge: Optional[MagicChallengeOut] = None
    army: list[MagicArmyStackOut]
    leadership: int = 0
    leadership_used: int = 0
    leadership_by_class: dict[str, int] = {}
    top: list[RankingEntry] = []


class MagicStartRequest(BaseModel):
    faction: Faction
    difficulty: Difficulty
    mode: Literal["quick", "hardcore", "adventure"] = "quick"
    hero_class: Literal["knight", "mage", "ranger"] = "knight"
    challenge: bool = False  # the weekly challenge: the week's map, quick mode, normal difficulty


class MagicVersionRequest(BaseModel):
    version: int


class MagicMoveRequest(BaseModel):
    version: int
    # The biggest map («Приключение») is 76 cells wide; the engine checks the cell itself.
    x: int = Field(ge=0, le=127)
    y: int = Field(ge=0, le=127)


class MagicActRequest(BaseModel):
    version: int
    unit: str = Field(max_length=16)
    action: Literal["move", "attack", "shoot", "defend", "wait"]
    target: Optional[str] = Field(default=None, max_length=16)
    x: Optional[int] = Field(default=None, ge=0, le=60)
    y: Optional[int] = Field(default=None, ge=0, le=60)


class MagicCastRequest(BaseModel):
    version: int
    spell: str = Field(max_length=16)
    target: Optional[str] = Field(default=None, max_length=16)


class MagicEffectOut(BaseModel):
    code: str
    label: str
    turns: int


class MagicStackOut(BaseModel):
    id: str
    unit: str
    unit_name: str
    emoji: str
    name: str
    card: Optional[MagicCardOut] = None
    tier: int
    count: int
    max_count: int
    hp: int
    top_hp: int
    atk: int
    defence: int
    dmin: int
    dmax: int
    spd: int
    ranged: bool
    flying: bool
    ability_text: str = ""
    trait: Optional[str] = None
    side: str = "me"
    x: Optional[int] = None
    y: Optional[int] = None
    effects: list[MagicEffectOut] = []
    defending: bool = False


class MagicMapObjectOut(BaseModel):
    id: str
    kind: str
    x: int
    y: int
    label: str
    taken_by: Optional[str] = None
    owner: Optional[str] = None
    level: Optional[int] = None
    emoji: str
    hint: str = ""
    guards: list[str] = []
    variant: Optional[str] = None  # the artifact code / the camp's creature
    offers: list["MagicOfferOut"] = []
    # Camps: how the guards compare with the player's army now — easy | even | hard.
    danger: Optional[str] = None
    style: Optional[str] = None  # a camp's style (its painted tents: dawn, ash, lost…)


class MagicOfferOut(BaseModel):
    unit: str
    unit_name: str
    tier: int
    count: int
    price: int
    bought: bool


MagicMapObjectOut.model_rebuild()


class MagicArtifactOut(BaseModel):
    code: str
    name: str
    emoji: str
    text: str


class MagicRunHeroOut(BaseModel):
    x: int
    y: int
    moves: int
    mana: int
    max_mana: int
    spell_power: int
    level: int
    morale: int
    gold: int = 0
    artifacts: list[MagicArtifactOut]
    spells: list[MagicSpellOut]
    # Where a long walk is heading (it goes on the next day); None — nowhere.
    goal: list[int] | None = None


class MagicTargetOut(BaseModel):
    target: str
    cells: list[list[int]]


class MagicBattleOut(BaseModel):
    kind: str
    foe_name: str
    round: int
    max_rounds: int
    turn_of: Optional[str] = None
    can_act: bool
    auto: bool
    can_cast: bool
    units: list[MagicStackOut]
    move_cells: list[list[int]] = []
    attack_targets: list[MagicTargetOut] = []
    shoot_targets: list[str] = []
    foe_mana: Optional[int] = None
    winner: Optional[str] = None
    won: Optional[bool] = None
    losses: int = 0
    rocks: list[list] = []  # [[x, y, "rock" | "tree"]] — cells nobody can stand on
    pitch: Optional[str] = None  # its own painted pitch ("lair"), else the map's biome


class MagicPackCardOut(BaseModel):
    name: str
    rarity: str
    image_path: Optional[str] = None


class MagicRunOut(BaseModel):
    id: int
    version: int
    status: str
    result: Optional[str] = None
    phase: str
    faction: str
    rival: str
    difficulty: str
    mode: str = "quick"
    challenge_week: Optional[str] = None
    day: int
    days: int
    score: int
    hero: MagicRunHeroOut
    bot: dict
    map_w: int
    map_h: int
    # [half width, min x+y, max x+y] of the playable band; None — the full square.
    map_shape: list[int] | None = None
    # The road as ordered castle-to-castle tracks (for drawing); [] on old runs.
    tracks: list[list[list[int]]] = []
    # The river's cells (some past the band's edge, drawn only) and the road's bridges over it.
    river: list[list[int]] = []
    bridges: list[list[int]] = []
    biome: str = "meadow"
    blocks: list[list] = []  # [x, y, kind, variant] — trees, rocks, mountains, water
    road: list[list[int]] = []
    decor: list[list[int]] = []
    seen: list[int] = []  # a bitmask of seen cells per row (fog of war)
    # The same rows as hex strings: a JS number keeps only 53 bits, the big maps are wider.
    seen_hex: list[str] = []
    objects: list[MagicMapObjectOut]
    reachable: list[list[int]]
    army: list[MagicStackOut]
    power: int
    battle: Optional[MagicBattleOut] = None
    events: list[dict] = []
    log: list[dict] = []
    reward_coins: int = 0
    rating_delta: int = 0
    xp_gained: int = 0
    level_up: bool = False
    pack_name: Optional[str] = None
    pack_cards: list[MagicPackCardOut] = []
    battles_won: int = 0
    notice: Optional[dict] = None  # the popup for what just happened
    pending: Optional[dict] = None  # a chest's choice or the hero's perk choice
    quests: list[dict] = []  # [{code, text, target, progress, done, failed}]
    event: Optional[dict] = None  # today's event: {code, icon, title, text}
    bot_style: Optional[dict] = None  # the rival's character: {code, label, text}
    perks: list[dict] = []  # [{code, emoji, title, text}] taken this run
    casualties: Optional[MagicCasualtiesOut] = None  # a finished run: what it cost the collection
    retry: Optional[dict] = None  # the second chance offer after a lost final
    hero_skin: str = "default"
    hero_class: str = "knight"
    castle_skin: str = "default"
    gold_coins: int = 0
    created_at: datetime


class MagicChooseRequest(BaseModel):
    version: int
    option: Literal["gold", "xp", "steps", "atk", "def", "magic", "luck", "scout"]


class MagicBuyRequest(BaseModel):
    version: int
    object_id: str = Field(max_length=16)
    index: int = Field(ge=0, le=5)


class MagicRetryRequest(BaseModel):
    version: int
    pay: Literal["coins", "credit"]


class MagicExtraRunOut(BaseModel):
    bonus_runs: int  # bought runs of this mode waiting today
    balance: int
    mode: str = "quick"
