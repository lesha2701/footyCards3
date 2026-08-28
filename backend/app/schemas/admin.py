from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Rarity


class DashboardChartPoint(BaseModel):
    date: str
    count: int


class RecentAdminActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int
    action: str
    entity_type: str
    entity_id: Optional[int]
    created_at: datetime


class DashboardOut(BaseModel):
    total_users: int
    active_users_7d: int
    total_packs_opened: int
    total_cards_issued: int
    total_trades: int
    coins_in_circulation: int
    registrations_by_day: list[DashboardChartPoint]
    pack_openings_by_day: list[DashboardChartPoint]
    recent_actions: list[RecentAdminActionOut]


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    balance: int
    is_admin: bool
    is_banned: bool
    game_rewards_blocked: bool
    is_trade_banned: bool
    arena_rating: int
    created_at: datetime
    last_seen_at: Optional[datetime]


class BalanceAdjustRequest(BaseModel):
    amount: int
    description: str = Field(min_length=1, max_length=255)


class GrantCardRequest(BaseModel):
    player_id: int


class GrantTrophyRequest(BaseModel):
    trophy_definition_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class ResetLimitsResponse(BaseModel):
    status: str = "ok"


class PackRarityStatOut(BaseModel):
    rarity: Rarity
    count: int
    percentage: float


class PackPreviewOut(BaseModel):
    simulations: int
    cards_per_open: int
    rarity_distribution: list[PackRarityStatOut]


class AdminActionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int
    admin_username: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[int]
    old_value: Optional[dict]
    new_value: Optional[dict]
    ip_address: Optional[str]
    extra: Optional[str]
    created_at: datetime


class StarsDonationSummaryOut(BaseModel):
    total_stars: int
    total_purchases: int


class TopSupporterOut(BaseModel):
    user_id: int
    user_telegram_id: int
    user_username: Optional[str] = None
    user_display_name: str
    total_stars: int
    purchase_count: int


class StarsPackPurchaseOut(BaseModel):
    id: int
    user_id: int
    user_telegram_id: int
    user_username: Optional[str] = None
    user_display_name: str
    pack_id: int
    pack_name: str
    stars_amount: int
    telegram_payment_charge_id: Optional[str] = None
    completed_at: datetime


class GameConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    club_creation_cost_coins: int
    club_daily_reward_coins: int
    club_tournament_cooldown_hours: int
    club_form_window_matches: int
    club_form_bonus_per_result: float
    club_tournament_budget_place_1: int
    club_tournament_budget_place_2: int
    club_tournament_budget_place_3: int
    club_tournament_budget_place_4: int
    club_tournament_budget_place_5: int
    club_tournament_budget_place_6: int
    club_tournament_budget_place_7: int
    club_tournament_budget_place_8: int
    memory_daily_reward_limit: int
    memory_reward_cap: int
    suspicious_memory_score_threshold: int
    match_reward_win: int
    match_reward_draw: int
    match_reward_loss: int
    difficulty_easy_multiplier: float
    difficulty_medium_multiplier: float
    difficulty_hard_multiplier: float
    suspicious_score_margin: int
    match_shot_miss_chance_min: float
    match_shot_miss_chance_max: float
    match_defender_block_chance_min: float
    match_defender_block_chance_max: float
    match_shot_type_in_box_weight: int
    match_shot_type_long_range_weight: int
    match_shot_type_empty_net_weight: int
    match_attack_shoot_miss_chance_min: float
    match_attack_shoot_miss_chance_max: float
    match_pass_fail_chance_min: float
    match_pass_fail_chance_max: float
    match_receiver_shot_miss_chance_min: float
    match_receiver_shot_miss_chance_max: float
    match_tackle_foul_chance_min: float
    match_tackle_foul_chance_max: float
    match_tackle_red_chance_min: float
    match_tackle_red_chance_max: float
    match_block_fail_chance_min: float
    match_block_fail_chance_max: float
    match_keeper_save_chance_min: float
    match_keeper_save_chance_max: float
    match_red_card_strength_penalty_pct: float
    match_penalty_gk_rating_penalty: int
    saboteur_line_base_reward: int
    saboteur_line_growth: float
    saboteur_daily_limit: int
    saboteur_max_steward_count: int
    penalty_reward_win: int
    penalty_reward_draw: int
    penalty_reward_loss: int
    penalty_bot_miss_chance: float
    penalty_daily_limit: int
    free_kick_period_min_ms: int
    free_kick_period_max_ms: int
    free_kick_base_stake: int
    free_kick_daily_limit: int
    hourly_game_limit: int
    matchmaking_enabled: bool
    wheel_enabled: bool
    leagues_enabled: bool
    free_pack_interval_hours: int
    free_pack_pack_slug: str
    chat_pack_interval_hours: int
    referral_referred_reward: int
    referral_referrer_reward: int
    hangman_daily_limit: int
    hangman_reward_correct: int
    hangman_max_wrong: int
    pairs_daily_limit: int
    pairs_reward_perfect: int
    pairs_reward_min: int
    pairs_error_bracket_size: int
    pairs_bracket_penalty: int
    pairs_bonus_coins: int
    tactico_challenge_expiry_hours: int
    tactico_round_timeout_hours: int
    tactico_phase_bonus_pct: float
    tactico_reward_win: int
    tactico_reward_draw: int
    tactico_reward_loss: int
    tactico_bot_optimal_pick_chance_easy: float
    tactico_bot_optimal_pick_chance_medium: float
    tactico_bot_optimal_pick_chance_hard: float
    tactico_max_legendary_cards: int
    tactico_max_epic_cards: int
    wheel_free_spins_per_day: int
    wheel_spin_cost_coins: int
    wheel_spin_cost_stars: int
    wheel_duplicate_badge_coins: int


class GameConfigUpdate(BaseModel):
    club_creation_cost_coins: Optional[int] = Field(default=None, ge=0)
    club_daily_reward_coins: Optional[int] = Field(default=None, ge=0)
    club_tournament_cooldown_hours: Optional[int] = Field(default=None, ge=0)
    club_form_window_matches: Optional[int] = Field(default=None, ge=1)
    club_form_bonus_per_result: Optional[float] = Field(default=None, ge=0, le=1)
    club_tournament_budget_place_1: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_2: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_3: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_4: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_5: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_6: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_7: Optional[int] = Field(default=None, ge=0)
    club_tournament_budget_place_8: Optional[int] = Field(default=None, ge=0)
    memory_daily_reward_limit: Optional[int] = Field(default=None, ge=0)
    memory_reward_cap: Optional[int] = Field(default=None, ge=0)
    suspicious_memory_score_threshold: Optional[int] = Field(default=None, ge=0)
    match_reward_win: Optional[int] = Field(default=None, ge=0)
    match_reward_draw: Optional[int] = Field(default=None, ge=0)
    match_reward_loss: Optional[int] = Field(default=None, ge=0)
    difficulty_easy_multiplier: Optional[float] = Field(default=None, ge=0)
    difficulty_medium_multiplier: Optional[float] = Field(default=None, ge=0)
    difficulty_hard_multiplier: Optional[float] = Field(default=None, ge=0)
    suspicious_score_margin: Optional[int] = Field(default=None, ge=0)
    match_shot_miss_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_shot_miss_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_defender_block_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_defender_block_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_shot_type_in_box_weight: Optional[int] = Field(default=None, ge=0)
    match_shot_type_long_range_weight: Optional[int] = Field(default=None, ge=0)
    match_shot_type_empty_net_weight: Optional[int] = Field(default=None, ge=0)
    match_attack_shoot_miss_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_attack_shoot_miss_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_pass_fail_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_pass_fail_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_receiver_shot_miss_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_receiver_shot_miss_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_tackle_foul_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_tackle_foul_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_tackle_red_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_tackle_red_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_block_fail_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_block_fail_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_keeper_save_chance_min: Optional[float] = Field(default=None, ge=0, le=1)
    match_keeper_save_chance_max: Optional[float] = Field(default=None, ge=0, le=1)
    match_red_card_strength_penalty_pct: Optional[float] = Field(default=None, ge=0, le=1)
    match_penalty_gk_rating_penalty: Optional[int] = Field(default=None, ge=0)
    saboteur_line_base_reward: Optional[int] = Field(default=None, ge=0)
    saboteur_line_growth: Optional[float] = Field(default=None, ge=1)
    saboteur_daily_limit: Optional[int] = Field(default=None, ge=0)
    saboteur_max_steward_count: Optional[int] = Field(default=None, ge=1)
    penalty_reward_win: Optional[int] = Field(default=None, ge=0)
    penalty_reward_draw: Optional[int] = Field(default=None, ge=0)
    penalty_reward_loss: Optional[int] = Field(default=None, ge=0)
    penalty_bot_miss_chance: Optional[float] = Field(default=None, ge=0, le=1)
    penalty_daily_limit: Optional[int] = Field(default=None, ge=0)
    free_kick_period_min_ms: Optional[int] = Field(default=None, ge=100)
    free_kick_period_max_ms: Optional[int] = Field(default=None, ge=100)
    free_kick_base_stake: Optional[int] = Field(default=None, ge=0)
    free_kick_daily_limit: Optional[int] = Field(default=None, ge=0)
    hourly_game_limit: Optional[int] = Field(default=None, ge=1)
    matchmaking_enabled: Optional[bool] = None
    wheel_enabled: Optional[bool] = None
    leagues_enabled: Optional[bool] = None
    free_pack_interval_hours: Optional[int] = Field(default=None, ge=1)
    free_pack_pack_slug: Optional[str] = None
    chat_pack_interval_hours: Optional[int] = Field(default=None, ge=1)
    referral_referred_reward: Optional[int] = Field(default=None, ge=0)
    referral_referrer_reward: Optional[int] = Field(default=None, ge=0)
    hangman_daily_limit: Optional[int] = Field(default=None, ge=0)
    hangman_reward_correct: Optional[int] = Field(default=None, ge=0)
    hangman_max_wrong: Optional[int] = Field(default=None, ge=1)
    pairs_daily_limit: Optional[int] = Field(default=None, ge=0)
    pairs_reward_perfect: Optional[int] = Field(default=None, ge=0)
    pairs_reward_min: Optional[int] = Field(default=None, ge=0)
    pairs_error_bracket_size: Optional[int] = Field(default=None, ge=1)
    pairs_bracket_penalty: Optional[int] = Field(default=None, ge=0)
    pairs_bonus_coins: Optional[int] = Field(default=None, ge=0)
    tactico_challenge_expiry_hours: Optional[int] = Field(default=None, ge=1)
    tactico_round_timeout_hours: Optional[int] = Field(default=None, ge=1)
    tactico_phase_bonus_pct: Optional[float] = Field(default=None, ge=0, le=1)
    tactico_reward_win: Optional[int] = Field(default=None, ge=0)
    tactico_reward_draw: Optional[int] = Field(default=None, ge=0)
    tactico_reward_loss: Optional[int] = Field(default=None, ge=0)
    tactico_bot_optimal_pick_chance_easy: Optional[float] = Field(default=None, ge=0, le=1)
    tactico_bot_optimal_pick_chance_medium: Optional[float] = Field(default=None, ge=0, le=1)
    tactico_bot_optimal_pick_chance_hard: Optional[float] = Field(default=None, ge=0, le=1)
    tactico_max_legendary_cards: Optional[int] = Field(default=None, ge=0, le=11)
    tactico_max_epic_cards: Optional[int] = Field(default=None, ge=0, le=11)
    wheel_free_spins_per_day: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_coins: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_stars: Optional[int] = Field(default=None, ge=0)
    wheel_duplicate_badge_coins: Optional[int] = Field(default=None, ge=0)


class SuspiciousMemorySessionOut(BaseModel):
    session_id: int
    user_id: int
    username: Optional[str]
    score: int
    reward_coins: int
    created_at: datetime


class SuspiciousMatchOut(BaseModel):
    match_id: int
    user_id: int
    username: Optional[str]
    user_score: int
    opponent_score: int
    reward_coins: int
    created_at: datetime


class CsvImportResultOut(BaseModel):
    created: int
    updated: int
    errors: list[dict]
