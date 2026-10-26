from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.schemas.monetization import GrantedRewardsOut, RewardBundleOut


class NewbieTaskOut(BaseModel):
    code: str
    label: str
    path: str
    coins: int
    pack_name: Optional[str] = None
    played: bool
    claimed: bool


class NewbieGiftOut(BaseModel):
    day: int
    coins: int = 0
    card_rarity: Optional[str] = None
    opens_on: date
    ready: bool
    claimed: bool


class NewbieOut(BaseModel):
    active: bool
    day: int = 1
    first_pack_done: bool = False
    # The best rarity the first pack holds (the welcome screen promises it).
    first_pack_top: Optional[str] = None
    squad_pack_done: bool = False
    squad_size: int = 11
    arena_played: bool = False
    arena_claimed: bool = False
    arena_rarity: Optional[str] = None
    tasks: list[NewbieTaskOut] = []
    gifts: list[NewbieGiftOut] = []
    bound_days: int = 0
    steps_done: int = 0
    steps_total: int = 0
    # All steps done: «Путь пройден» with its reward (badge «Дебютант» …).
    finale_ready: bool = False
    finale: Optional[RewardBundleOut] = None


class NewbieClaimOut(BaseModel):
    rewards: GrantedRewardsOut
    state: NewbieOut


class NewbieFunnelStepOut(BaseModel):
    code: str
    label: str
    players: int


class NewbieFunnelOut(BaseModel):
    days: int
    started: int
    completed: int
    steps: list[NewbieFunnelStepOut]
