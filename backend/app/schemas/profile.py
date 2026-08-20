from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.badge import BadgeOut
from app.schemas.player import PlayerOut


class ProfilePublicOut(BaseModel):
    id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    level: int
    arena_rating: int
    arena_rank: int
    league_rank: int
    active_badge: Optional[BadgeOut] = None
    matches_won: int
    matches_drawn: int
    matches_lost: int
    memory_best_score: int
    unique_cards: int
    total_cards: int
    rarest_card: Optional[PlayerOut]
    packs_opened: int
    referral_count: int
    tactics_rating: int
    tactics_matches_won: int
    tactics_matches_drawn: int
    tactics_matches_lost: int
    penalty_rating: int
    penalty_matches_won: int
    penalty_matches_drawn: int
    penalty_matches_lost: int


class ProfilePrivateOut(ProfilePublicOut):
    telegram_id: int
    balance: int
    experience: int
    is_admin: bool
    telegram_bot_username: str
    accept_trades: bool
    referral_reward_pending: bool
    referral_referrer_reward: int
    referral_referred_reward: int
    daily_login_streak: int


class ProfileSettingsUpdate(BaseModel):
    accept_trades: Optional[bool] = None
    # Which owned badge to display next to the player's name; null unequips.
    active_badge_id: Optional[int] = None
