from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class KontraCardOut(BaseModel):
    card_id: int
    display_name: str
    position: str
    rarity: str
    rating: int
    image_path: Optional[str] = None
    # common / rare / epic / legendary / diamond / path / my_player
    tier: str


class KontraAbilityOut(BaseModel):
    code: str
    name: str
    description: str
    cooldown: int
    cd: int = 0
    ready: bool = True
    # The leader's ultimate: ready when the squad's charge is full.
    ult: bool = False


class KontraPassiveOut(BaseModel):
    code: str
    name: str
    description: str


class KontraTacticOut(BaseModel):
    code: str
    name: str
    bonus: str
    beats: str
    beats_name: str


class KontraFighterOut(BaseModel):
    """A card as a «Контратака» fighter (squad screen)."""

    card: KontraCardOut
    role: str
    role_label: str
    hp: int
    atk: int
    defence: int
    spd: int
    abilities: list[KontraAbilityOut]
    passive: Optional[KontraPassiveOut] = None
    gear_count: int = 0


class KontraSquadOut(BaseModel):
    fighters: list[KontraFighterOut]
    leader_id: Optional[int] = None
    power: int
    chemistry_pct: int
    chemistry_label: Optional[str] = None
    leader_aura: Optional[str] = None
    options: list[KontraFighterOut]
    size: int
    tactic: Optional[str] = None
    tactics: list[KontraTacticOut] = []
    tactic_edge_pct: int = 0
    leader_ult: Optional[KontraAbilityOut] = None


class KontraSquadSetRequest(BaseModel):
    cards: list[int]
    leader: int


class KontraEffectOut(BaseModel):
    code: str
    label: str
    turns: int


class KontraUnitOut(BaseModel):
    id: str
    side: str
    name: str
    card: Optional[KontraCardOut] = None
    role: str
    tier: str
    hp: int
    max_hp: int
    meter_pct: int
    alive: bool
    leader: bool = False
    effects: list[KontraEffectOut] = []
    abilities: list[KontraAbilityOut] = []
    passive: Optional[KontraPassiveOut] = None


class KontraGearOut(BaseModel):
    id: int
    slot: str
    slot_label: str
    set_code: str
    set_name: str
    rarity: str
    rarity_label: str
    stat: str
    pct: int
    card_id: Optional[int] = None


class KontraBattleOut(BaseModel):
    id: int
    version: int
    mode: str
    status: str
    result: Optional[str] = None
    opponent_name: str
    manual: bool
    auto: bool
    turn_of: Optional[str] = None
    can_act: bool = False
    round: int
    max_rounds: int
    units: list[KontraUnitOut]
    # The events produced by the request that returned this (to animate),
    # or the last ones on a plain read.
    events: list[dict] = []
    damage: int = 0
    reward_coins: int = 0
    rating_delta: int = 0
    gear_drop: Optional[KontraGearOut] = None
    boss_name: Optional[str] = None
    boss_tagline: Optional[str] = None
    boss_code: Optional[str] = None
    created_at: datetime
    tactic_me: Optional[KontraTacticOut] = None
    tactic_foe: Optional[KontraTacticOut] = None
    tactic_edge_pct: int = 0
    # Ultimate charge of each side, 0..100.
    charge_me: int = 0
    charge_foe: int = 0
    revenge: bool = False


class KontraActRequest(BaseModel):
    version: int
    unit_id: str
    ability: str
    target_id: Optional[str] = None


class KontraAutoRequest(BaseModel):
    version: int


class KontraStartRequest(BaseModel):
    manual: bool = False


class KontraArenaStartRequest(KontraStartRequest):
    offer: int


class KontraOfferOut(BaseModel):
    index: int
    name: str
    rating: int
    power: int
    is_bot: bool
    cards: list[KontraCardOut]
    tactic: Optional[KontraTacticOut] = None
    revenge: bool = False


class KontraLeagueTierOut(BaseModel):
    name: str
    icon: str
    at: int
    coins: int


class KontraLeagueOut(BaseModel):
    """The weekly arena league, by the best rating of the week."""

    index: int
    name: str
    icon: str
    week_best: int
    coins: int
    next_name: Optional[str] = None
    next_at: Optional[int] = None
    next_coins: Optional[int] = None
    week_ends: datetime
    tiers: list[KontraLeagueTierOut] = []


class KontraLeagueRewardOut(BaseModel):
    name: str
    icon: str
    coins: int
    best: int


class KontraDefenseItemOut(BaseModel):
    battle_id: int
    attacker_name: str
    attacker_rating: int
    result: str  # win | loss — from the defender's side
    survivors: int
    created_at: datetime
    is_new: bool
    can_revenge: bool


class KontraDefenseOut(BaseModel):
    items: list[KontraDefenseItemOut]
    wins: int
    losses: int


class KontraTacticRequest(BaseModel):
    tactic: Optional[str] = None


class KontraArenaOut(BaseModel):
    rating: int
    rank: Optional[int] = None
    offers: list[KontraOfferOut]
    rewarded_today: int
    daily_limit: int
    reward_win: int
    reward_loss: int
    rating_win: int
    rating_loss: int
    tactic: Optional[KontraTacticOut] = None
    tactics: list[KontraTacticOut] = []
    tactic_edge_pct: int = 0
    league: Optional[KontraLeagueOut] = None
    defense_unread: int = 0


class KontraBossOut(BaseModel):
    code: str
    name: str
    tagline: str
    week_start: datetime
    week_hp: int
    week_damage: int
    phase: int
    my_damage: int
    my_best: int
    club_name: Optional[str] = None
    club_damage: int = 0
    attempts_left: int
    attempts_per_day: int
    reward_tiers: list[list[int]]
    top: list[dict] = []


class KontraHubOut(BaseModel):
    enabled: bool
    squad_ready: bool
    rating: int
    active_battle_id: Optional[int] = None
    boss_name: str
    boss_attempts_left: int
    gear_count: int
    defense_unread: int = 0
    league: Optional[KontraLeagueOut] = None
    league_reward: Optional[KontraLeagueRewardOut] = None


class KontraGearListOut(BaseModel):
    items: list[KontraGearOut]
    sets: list[dict]
    chest_coins: int
    chest_stars: int
    balance: int


class KontraGearEquipRequest(BaseModel):
    card_id: Optional[int] = None
