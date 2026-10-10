from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Rarity


class PlaceSkillTokenReward(BaseModel):
    skill_code: str
    quantity: int = Field(ge=1, le=100)


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
    club_match_reward_win: int
    club_match_reward_draw: int
    club_match_reward_loss: int
    club_member_match_reward_win: int
    club_member_match_reward_draw: int
    club_member_match_reward_loss: int
    club_training_boost_pct: float
    club_training_uses_per_tournament: int
    club_games_hourly_limit: int
    club_game_daily_reward_limit: int
    club_game_reward_cap: int
    club_penalty_daily_reward_limit: int
    club_penalty_reward_win: int
    club_penalty_reward_loss: int
    club_penalty_bot_miss_chance: float
    club_position_match_daily_reward_limit: int
    club_position_match_max_mistakes: int
    club_position_match_reward_perfect: int
    club_position_match_reward_min: int
    club_position_match_penalty_per_mistake: int
    fut_draft_entry_cost: int
    fut_draft_weak_chance: int
    fut_draft_normal_chance: int
    fut_draft_strong_chance: int
    fut_draft_top_chance: int
    fut_draft_jackpot_chance: int
    fut_draft_reward_win_0: int
    fut_draft_reward_win_1: int
    fut_draft_reward_win_2: int
    fut_draft_reward_win_3: int
    fut_draft_reward_win_4: int
    fut_draft_club_bonus_per_extra: int
    fut_draft_country_bonus_per_extra: int
    fut_draft_round_bot_boost_pct: float
    club_tactical_tackle_attempt_chance: float
    club_tactical_injury_chance: float
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
    bot_daily_digest_enabled: bool = False
    bot_daily_digest_hour: int = 18
    shop_daily_offer_enabled: bool = False
    shop_daily_offer_discount_pct: int = 25
    shop_daily_offer_pack_id: Optional[int] = None
    career_enabled: bool = True
    career_place_rewards: list[int] = []
    career_difficulty_reward_pct: list[int] = []
    career_difficulty_rating_offset: list[int] = []
    career_match_reward_win: int = 30
    career_match_reward_draw: int = 10
    career_bot_growth_tenths: int = 3
    career_fatigue_per_match: int = 35
    career_fatigue_recovery: int = 40
    career_fatigue_penalty_pct: int = 15
    career_injury_chance_pct: int = 3
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
    tactico_max_diamond_cards: int
    match_max_diamond_cards: int
    diamond_rating_cap: int
    diamond_rating_cap_enabled: bool
    wheel_free_spins_per_day: int
    wheel_spin_cost_coins: int
    wheel_spin_cost_stars: int
    wheel_duplicate_badge_coins: int
    bingo_reward_coins: int
    bingo_reward_pack_id: Optional[int] = None
    card_skills_enabled: bool = True
    card_skill_level_1_bonus_pp: int = 2
    card_skill_level_2_bonus_pp: int = 4
    card_skill_level_3_bonus_pp: int = 6
    card_skill_event_bonus_cap_pp: int = 8
    card_skill_probability_floor_pct: int = 2
    card_skill_probability_ceiling_pct: int = 95
    card_skill_assign_token_cost: int = 1
    card_skill_assign_coin_cost: int = 0
    card_skill_upgrade_2_token_cost: int = 2
    card_skill_upgrade_2_coin_cost: int = 400
    card_skill_upgrade_3_token_cost: int = 4
    card_skill_upgrade_3_coin_cost: int = 1200
    card_skill_replace_token_cost: int = 1
    card_skill_replace_coin_cost: int = 300
    ptour_place_skill_tokens: list[Optional[PlaceSkillTokenReward]] = []


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
    club_match_reward_win: Optional[int] = Field(default=None, ge=0)
    club_match_reward_draw: Optional[int] = Field(default=None, ge=0)
    club_match_reward_loss: Optional[int] = Field(default=None, ge=0)
    club_member_match_reward_win: Optional[int] = Field(default=None, ge=0)
    club_member_match_reward_draw: Optional[int] = Field(default=None, ge=0)
    club_member_match_reward_loss: Optional[int] = Field(default=None, ge=0)
    club_training_boost_pct: Optional[float] = Field(default=None, ge=0, le=1)
    club_training_uses_per_tournament: Optional[int] = Field(default=None, ge=0)
    club_games_hourly_limit: Optional[int] = Field(default=None, ge=1)
    club_game_daily_reward_limit: Optional[int] = Field(default=None, ge=0)
    club_game_reward_cap: Optional[int] = Field(default=None, ge=0)
    club_penalty_daily_reward_limit: Optional[int] = Field(default=None, ge=0)
    club_penalty_reward_win: Optional[int] = Field(default=None, ge=0)
    club_penalty_reward_loss: Optional[int] = Field(default=None, ge=0)
    club_penalty_bot_miss_chance: Optional[float] = Field(default=None, ge=0, le=1)
    club_position_match_daily_reward_limit: Optional[int] = Field(default=None, ge=0)
    club_position_match_max_mistakes: Optional[int] = Field(default=None, ge=1)
    club_position_match_reward_perfect: Optional[int] = Field(default=None, ge=0)
    club_position_match_reward_min: Optional[int] = Field(default=None, ge=0)
    club_position_match_penalty_per_mistake: Optional[int] = Field(default=None, ge=0)
    fut_draft_entry_cost: Optional[int] = Field(default=None, ge=0)
    fut_draft_weak_chance: Optional[int] = Field(default=None, ge=0, le=100)
    fut_draft_normal_chance: Optional[int] = Field(default=None, ge=0, le=100)
    fut_draft_strong_chance: Optional[int] = Field(default=None, ge=0, le=100)
    fut_draft_top_chance: Optional[int] = Field(default=None, ge=0, le=100)
    fut_draft_jackpot_chance: Optional[int] = Field(default=None, ge=0, le=100)
    fut_draft_reward_win_0: Optional[int] = Field(default=None, ge=0)
    fut_draft_reward_win_1: Optional[int] = Field(default=None, ge=0)
    fut_draft_reward_win_2: Optional[int] = Field(default=None, ge=0)
    fut_draft_reward_win_3: Optional[int] = Field(default=None, ge=0)
    fut_draft_reward_win_4: Optional[int] = Field(default=None, ge=0)
    fut_draft_club_bonus_per_extra: Optional[int] = Field(default=None, ge=0)
    fut_draft_country_bonus_per_extra: Optional[int] = Field(default=None, ge=0)
    fut_draft_round_bot_boost_pct: Optional[float] = Field(default=None, ge=0, le=100)
    club_tactical_tackle_attempt_chance: Optional[float] = Field(default=None, ge=0, le=1)
    club_tactical_injury_chance: Optional[float] = Field(default=None, ge=0, le=1)
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
    bot_daily_digest_enabled: Optional[bool] = None
    bot_daily_digest_hour: Optional[int] = Field(default=None, ge=0, le=23)
    shop_daily_offer_enabled: Optional[bool] = None
    shop_daily_offer_discount_pct: Optional[int] = Field(default=None, ge=1, le=90)
    # 0 = rotate through active coin packs by date (stored as NULL).
    shop_daily_offer_pack_id: Optional[int] = Field(default=None, ge=0)
    career_enabled: Optional[bool] = None
    # 8 places; 3 difficulties (Любитель, Профи, Легенда).
    career_place_rewards: Optional[list[int]] = Field(default=None, min_length=8, max_length=8)
    career_difficulty_reward_pct: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    career_difficulty_rating_offset: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    career_match_reward_win: Optional[int] = Field(default=None, ge=0)
    career_match_reward_draw: Optional[int] = Field(default=None, ge=0)
    career_bot_growth_tenths: Optional[int] = Field(default=None, ge=0, le=30)
    career_fatigue_per_match: Optional[int] = Field(default=None, ge=0, le=100)
    career_fatigue_recovery: Optional[int] = Field(default=None, ge=0, le=100)
    career_fatigue_penalty_pct: Optional[int] = Field(default=None, ge=0, le=60)
    career_injury_chance_pct: Optional[int] = Field(default=None, ge=0, le=50)
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
    tactico_max_diamond_cards: Optional[int] = Field(default=None, ge=0, le=11)
    match_max_diamond_cards: Optional[int] = Field(default=None, ge=0, le=11)
    diamond_rating_cap: Optional[int] = Field(default=None, ge=1, le=99)
    diamond_rating_cap_enabled: Optional[bool] = None
    wheel_free_spins_per_day: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_coins: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_stars: Optional[int] = Field(default=None, ge=0)
    wheel_duplicate_badge_coins: Optional[int] = Field(default=None, ge=0)
    bingo_reward_coins: Optional[int] = Field(default=None, ge=0)
    bingo_reward_pack_id: Optional[int] = Field(default=None)
    card_skills_enabled: Optional[bool] = None
    card_skill_level_1_bonus_pp: Optional[int] = Field(default=None, ge=0, le=20)
    card_skill_level_2_bonus_pp: Optional[int] = Field(default=None, ge=0, le=20)
    card_skill_level_3_bonus_pp: Optional[int] = Field(default=None, ge=0, le=20)
    card_skill_event_bonus_cap_pp: Optional[int] = Field(default=None, ge=0, le=30)
    card_skill_probability_floor_pct: Optional[int] = Field(default=None, ge=0, le=50)
    card_skill_probability_ceiling_pct: Optional[int] = Field(default=None, ge=50, le=100)
    card_skill_assign_token_cost: Optional[int] = Field(default=None, ge=0, le=100)
    card_skill_assign_coin_cost: Optional[int] = Field(default=None, ge=0)
    card_skill_upgrade_2_token_cost: Optional[int] = Field(default=None, ge=0, le=100)
    card_skill_upgrade_2_coin_cost: Optional[int] = Field(default=None, ge=0)
    card_skill_upgrade_3_token_cost: Optional[int] = Field(default=None, ge=0, le=100)
    card_skill_upgrade_3_coin_cost: Optional[int] = Field(default=None, ge=0)
    card_skill_replace_token_cost: Optional[int] = Field(default=None, ge=0, le=100)
    card_skill_replace_coin_cost: Optional[int] = Field(default=None, ge=0)
    ptour_place_skill_tokens: Optional[list[Optional[PlaceSkillTokenReward]]] = Field(default=None, max_length=16)

    @field_validator("ptour_place_skill_tokens")
    @classmethod
    def _engine_supported_skills_only(cls, value):
        # Deferred import: services import schemas, not the other way round.
        from app.services.card_skill_catalog import SKILL_DEFINITIONS

        for entry in value or []:
            if entry is None:
                continue
            definition = SKILL_DEFINITIONS.get(entry.skill_code)
            if definition is None or not definition.engine_supported:
                raise ValueError(f"skill '{entry.skill_code}' cannot be granted")
        return value


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


class EconomyTypeRow(BaseModel):
    type: str
    inflow: int
    outflow: int
    count: int


class EconomyDayRow(BaseModel):
    date: str
    inflow: int
    outflow: int


class EconomyReportOut(BaseModel):
    days: int
    total_inflow: int
    total_outflow: int
    net: int
    by_type: list[EconomyTypeRow]
    daily: list[EconomyDayRow]
    packs_opened: int
    skill_tokens_granted: int
    skill_tokens_spent: int
    skill_coins_spent: int


class PackRarityValueRow(BaseModel):
    rarity: str
    probability: float
    avg_quick_sell: float
    pool_size: int


class PackExpectedValueOut(BaseModel):
    pack_id: int
    price: int
    card_count: int
    expected_quick_sell_value: float
    value_to_price: Optional[float] = None
    rarities: list[PackRarityValueRow]
