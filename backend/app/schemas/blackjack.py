from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.wheel import WheelPrizeOut, WheelSpinResultOut


class BlackjackCardOut(BaseModel):
    # hidden=True is the bot's face-down card: rank/suit are then None.
    hidden: bool = False
    rank: Optional[str] = None
    suit: Optional[str] = None


class BlackjackMatchOut(BaseModel):
    id: int
    status: Literal["in_progress", "finished"]
    entry_source: str
    player_cards: list[BlackjackCardOut]
    player_total: int
    player_soft: bool
    dealer_cards: list[BlackjackCardOut]
    # While in progress: only the face-up card's value.
    dealer_total: int
    outcome: Optional[str] = None
    outcome_reason: Optional[str] = None
    # The wheel actually rolled: golden (win) / jackpot (hat-trick), or the
    # next pool down if an admin left that one empty.
    reward_pool: Optional[Literal["golden", "jackpot", "regular"]] = None
    prize: Optional[WheelPrizeOut] = None
    consolation_coins: int = 0
    created_at: datetime
    finished_at: Optional[datetime] = None


class BlackjackActionOut(BaseModel):
    match: BlackjackMatchOut
    new_balance: int
    # Only on the request that finished a winning hand — the full grant
    # (pack cards, card, badge) for the wheel animation + reveal.
    spin_result: Optional[WheelSpinResultOut] = None


class BlackjackStatusOut(BaseModel):
    enabled: bool
    free_per_day: int
    free_remaining: int
    paid_entries: int
    replay_entries: int
    paid_bought_today: int
    paid_daily_limit: int
    stars_cost: int
    consolation_coins: int
    next_reset_at: datetime
    active_match: Optional[BlackjackMatchOut] = None
    golden_prizes: list[WheelPrizeOut]
    jackpot_prizes: list[WheelPrizeOut]
