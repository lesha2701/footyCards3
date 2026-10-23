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


class KontraPassiveOut(BaseModel):
    code: str
    name: str
    description: str


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
    created_at: datetime


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


class KontraGearListOut(BaseModel):
    items: list[KontraGearOut]
    sets: list[dict]
    chest_coins: int
    chest_stars: int
    balance: int


class KontraGearEquipRequest(BaseModel):
    card_id: Optional[int] = None
