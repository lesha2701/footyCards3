from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.badge import BadgeOut
from app.schemas.monetization import EquippedCosmeticsOut, RewardBundleOut
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
    # Equipped cosmetics (style keys) and whether the club pass is on.
    cosmetics: EquippedCosmeticsOut = EquippedCosmeticsOut()
    club_pass_active: bool = False
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


class ReferralMilestoneOut(BaseModel):
    count: int
    reward: RewardBundleOut
    reached: bool


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
    # A friend counts after this many days of play (referral_service).
    referral_active_days: int = 3
    referral_milestones: list[ReferralMilestoneOut] = []
    daily_login_streak: int


class ProfileSettingsUpdate(BaseModel):
    accept_trades: Optional[bool] = None
    # Which owned badge to display next to the player's name; null unequips.
    active_badge_id: Optional[int] = None


class AttentionOut(BaseModel):
    incoming_trades: int = 0
    match_challenges: int = 0
    active_friend_matches: int = 0
    league_unseen_rewards: int = 0
    friend_requests: int = 0
    career_invites: int = 0
