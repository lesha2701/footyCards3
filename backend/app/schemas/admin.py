from datetime import datetime
from typing import Annotated, Literal, Optional

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


class StarsPaymentReceiptOut(BaseModel):
    """One received Stars payment and how its delivery went (admin view)."""

    id: int
    telegram_payment_charge_id: str
    telegram_user_id: int
    user_id: Optional[int] = None
    user_username: Optional[str] = None
    user_display_name: Optional[str] = None
    product: str
    stars_amount: int
    status: Literal["pending", "delivered", "failed", "refunded"]
    attempts: int
    last_error: Optional[str] = None
    next_attempt_at: Optional[datetime] = None
    # Still being retried by the bot on its own (false = waits for an admin).
    auto_retry: bool
    created_at: datetime
    delivered_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None


class StarsPaymentProblemCountOut(BaseModel):
    count: int


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
    arena_style_matchup_bonus_pct: int = 6
    arena_share_exponent: float = 1.2
    arena_shot_exponent: float = 0.8
    arena_edge_rating_per_10pct: float = 2.0
    arena_edge_rating_max: int = 12
    arena_formation_effect_pct: int = 100
    arena_points_k: int = 40
    arena_points_scale: int = 400
    arena_shield_matches: int = 3
    arena_matchmaking_window: int = 150
    arena_division_min_points: list[int] = []
    arena_division_reward_coins: list[int] = []
    arena_division_coin_pct: list[int] = []
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
    trades_enabled: bool = True
    leagues_enabled: bool
    free_pack_interval_hours: int
    bot_daily_digest_enabled: bool = False
    bot_daily_digest_hour: int = 18
    shop_daily_offer_enabled: bool = False
    shop_daily_offer_discount_pct: int = 25
    shop_daily_offer_pack_id: Optional[int] = None
    club_league_enabled: bool = True
    club_league_points_game: int = 2
    club_league_points_pack: int = 5
    club_league_points_task: int = 3
    club_league_member_weekly_cap: int = 200
    club_league_rewards: list[int] = []
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
    career_yellow_chance_pct: int = 8
    career_red_chance_pct: int = 1
    career_yellows_for_ban: int = 3
    career_form_max: int = 2
    career_reminders_enabled: bool = True
    career_tactics_tuning: dict = {}
    career_familiarity_axis_keep_pct: int = 80
    career_squad_size: int = 22
    career_ambition_bonus_pct: list[int] = []
    career_ambition_rep_success: list[int] = []
    career_ambition_rep_fail: list[int] = []
    career_rep_title: int = 25
    career_rep_promotion: int = 10
    career_rep_relegation: int = -10
    career_rep_levels: list[int] = []
    career_cup_enabled: bool = True
    career_cup_rewards: list[int] = []
    career_rep_cup: int = 15
    career_offseason_auto: bool = True
    career_inactive_days: int = 3
    career_core_min: int = 15
    career_core_keep_pct: int = 50
    career_camp_physical_pct: int = 30
    career_camp_physical_rounds: int = 3
    career_camp_tactical_tenths: int = 40
    career_tenure_minutes_per_point: int = 900
    career_tenure_max: int = 2
    career_division_club_count: int = 10
    career_live_enabled: bool = True
    career_halftime_minutes: int = 10
    career_achievement_reward: int = 150
    career_digest_enabled: bool = True
    career_familiarity_step_tenths: int = 20
    career_familiarity_max_tenths: int = 90
    career_familiarity_keep_pct: int = 50
    career_max_plan_rules: int = 3
    career_max_substitutions: int = 3
    career_bot_counter_chance_pct: list[int] = []
    career_division_count: int = 5
    career_division_promote: int = 2
    career_division_relegate: int = 2
    career_division_rating_offset: list[int] = []
    career_division_reward_pct: list[int] = []
    career_division_bot_level: list[str] = []
    my_player_enabled: bool = True
    my_player_xp_per_reward: int = 10
    my_player_xp_daily_cap: int = 200
    my_player_xp_career_match: int = 15
    my_player_xp_level_base: int = 100
    my_player_xp_level_step: int = 20
    my_player_points_per_level: int = 2
    my_player_rating_cap: int = 88
    my_player_tier_thresholds: list[int] = []
    my_player_training_xp_base: int = 20
    my_player_training_xp_per_hit: int = 15
    my_player_cosmetic_prices: dict[str, int] = {}
    my_player_extra_trainings_max: int = 3
    my_player_extra_training_coins: int = 300
    my_player_extra_training_stars: int = 15
    my_player_streak_days: int = 7
    my_player_streak_tokens: int = 1
    my_player_freshness_per_match: int = 15
    my_player_freshness_regen_per_hour: int = 1
    my_player_freshness_training: int = 20
    my_player_fatigue_max_penalty: int = 5
    my_player_duels_per_day: int = 5
    my_player_duel_reward_win: int = 30
    my_player_duel_reward_draw: int = 10
    my_player_duel_xp: int = 10
    my_player_role_change_coins: int = 25000
    my_player_role_change_stars: int = 300
    my_player_cosmetic_stars_prices: dict[str, int] = {}
    player_career_level_ratings: list[int] = []
    player_career_level_salary: list[int] = []
    player_career_level_prestige: list[int] = []
    player_career_star_prestige: list[int] = []
    player_career_star_salary_pct: int = 20
    player_career_prestige_salary_cap: int = 50
    player_career_contract_seasons: int = 2
    player_career_free_agent_level: int = 4
    player_career_offers_max: int = 3
    player_career_haggle_base: int = 90
    player_career_haggle_raise_penalty: int = 2
    player_career_haggle_repeat_penalty: int = 15
    player_career_cl_places: int = 2
    player_career_cl_rewards: list[int] = []
    player_career_cl_prestige: int = 40
    player_career_national_prestige: int = 150
    player_career_national_rewards: list[int] = []
    player_career_national_win_prestige: int = 30
    player_career_golden_ball_min_matches: int = 8
    player_career_golden_ball_coins: int = 3000
    player_career_golden_ball_prestige: int = 50
    player_career_moments: int = 2
    player_career_moment_hit_pct: int = 18
    player_career_moment_window_hours: int = 6
    player_career_bench_gap: int = 3
    player_career_bench_play_pct: int = 40
    player_career_trust_starter: int = 70
    player_career_trust_captain: int = 85
    player_career_captain_salary_pct: int = 10
    player_career_injury_freshness: int = 40
    player_career_injury_max_pct: int = 20
    player_career_heal_coins: int = 500
    player_career_heal_stars: int = 20
    player_career_refresh_coins: int = 300
    player_career_refresh_stars: int = 15
    player_career_event_every: int = 3
    player_career_event_coins: int = 100
    player_career_event_prestige: int = 5
    player_career_derby_multiplier: int = 2
    player_career_pro_stars: int = 299
    player_career_pro_days: int = 30
    player_career_pro_xp_pct: int = 50
    player_career_agent_stars: int = 50
    player_career_agent_haggle_bonus: int = 15
    player_career_save_offer_stars: int = 30
    player_career_fast_season_enabled: bool = False
    player_career_fast_season_stars: int = 100
    player_career_fast_round_minutes: int = 120
    player_career_chest_coins_min: int = 50
    player_career_chest_coins_max: int = 200
    player_career_chest_token_pct: int = 10
    player_career_weekly_goals: int = 5
    player_career_weekly_matches: int = 10
    player_career_weekly_rating_x10: int = 70
    player_career_weekly_coins: list[int] = []
    player_career_friends_rewards: list[int] = []
    manager_enabled: bool = True
    manager_found_cost: int = 3000
    manager_min_level: int = 3
    manager_max_live: int = 5
    manager_squad_max: int = 22
    manager_league_size: int = 16
    manager_divisions: int = 10
    manager_promote: int = 2
    manager_preseason_hours: int = 72
    manager_style_edge_pct: int = 4
    ptour_style_edge_pct: int = 4
    ptour_formation_effect_pct: int = 100
    manager_formation_effect_pct: int = 100
    manager_wage_pct: int = 10
    manager_loan_fee_pct: int = 20
    manager_sell_back_pct: int = 50
    manager_live_wage_max: int = 3000
    manager_wage_eur_per_coin: int = 1000
    manager_form_bonus_pct: int = 5
    manager_form_bonus_cap: int = 50
    manager_income_win: int = 300000
    manager_income_draw: int = 150000
    manager_income_loss: int = 60000
    manager_ticket_eur_per_level: int = 20000
    manager_sponsor_eur_per_level: int = 100000
    manager_merch_eur_per_level: int = 60000
    manager_budget_per_base_level: int = 20000
    manager_base_bonus_cap_pct: int = 60
    manager_promotion_bonus_pct: int = 50
    manager_parachute_pct: int = 33
    manager_match_xp: int = 30
    manager_freshness_cost: int = 0
    manager_merch_cap_eur: int = 15000000
    manager_pro_stars: int = 299
    manager_pro_days: int = 30
    manager_value_ratings: list[int] = []
    manager_value_eur: list[int] = []
    manager_division_budget: list[int] = []
    manager_division_income_pct: list[int] = []
    manager_division_wage_pct: list[int] = []
    manager_division_rating: list[int] = []
    manager_place_rewards: list[int] = []
    manager_place_budget: list[int] = []
    manager_slots: list[str] = []
    manager_cosmetics: list[dict] = []
    manager_merch: list[dict] = []
    player_career_objective_coins: int = 150
    player_career_objective_rep: int = 5
    player_career_enabled: bool = True
    player_career_rating_margin: int = 5
    player_career_rep_per_goal: int = 3
    player_career_rep_per_assist: int = 2
    player_career_rep_per_win: int = 2
    player_career_rep_title: int = 30
    player_career_match_reward_win: int = 25
    player_career_match_reward_draw: int = 10
    player_career_goal_reward: int = 10
    player_career_match_xp: int = 15
    player_career_place_rewards: list[int] = []
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
    stratego_board_size: int
    stratego_max_legendary_cards: int
    stratego_max_diamond_cards: int
    stratego_min_rare_cards: int
    stratego_min_common_cards: int
    stratego_my_player_xp: int
    stratego_tackler_max_rarity: str
    stratego_provocateur_max_rarity: str
    stratego_speedster_max_rarity: str
    stratego_bot_easy_reward_pct: int
    stratego_live_move_seconds: int
    stratego_skill_bonus_per_level: int
    stratego_puzzle_reward: int
    stratego_tackler_count: int
    stratego_speedster_count: int
    stratego_wall_count: int
    stratego_regular_count: int
    stratego_move_limit: int
    stratego_challenge_expiry_hours: int
    stratego_move_timeout_hours: int
    stratego_max_auto_moves: int
    stratego_reward_win: int
    stratego_reward_draw: int
    stratego_reward_loss: int
    stratego_daily_limit: int
    magnate_start_money: int
    magnate_pass_start_bonus: int
    magnate_jail_fine: int
    magnate_max_jail_turns: int
    magnate_fine_amount: int
    magnate_building_sell_pct: int
    magnate_max_rounds: int
    magnate_time_limit_minutes: int
    magnate_turn_seconds: int
    magnate_max_missed_turns: int
    magnate_lobby_wait_seconds: int
    magnate_room_wait_minutes: int
    magnate_bot_buy_reserve: int
    magnate_bot_build_reserve: int
    magnate_bot_reward_pct: int
    magnate_daily_limit: int
    magnate_place_rewards: list[int] = []
    magnate_stadium_rents: list[int] = []
    # NULL = built-in default board / cards (GET /admin/games/magnate-defaults).
    magnate_board: Optional[dict] = None
    magnate_cards: Optional[dict] = None
    match_max_diamond_cards: int
    diamond_rating_cap: int
    diamond_rating_cap_enabled: bool
    wheel_free_spins_per_day: int
    wheel_spin_cost_coins: int
    wheel_spin_cost_stars: int
    wheel_duplicate_badge_coins: int
    blackjack_enabled: bool = True
    blackjack_free_per_day: int = 1
    blackjack_stars_cost: int = 10
    blackjack_paid_daily_limit: int = 10
    blackjack_consolation_coins: int = 25
    mordoboi_enabled: bool = True
    mordoboi_rounds: int = 3
    mordoboi_exchanges_per_round: int = 4
    mordoboi_base_hp: int = 100
    mordoboi_reward_win: int = 80
    mordoboi_reward_draw: int = 40
    mordoboi_reward_loss: int = 25
    mordoboi_reward_ko_bonus: int = 20
    mordoboi_daily_limit: int = 10
    mordoboi_bot_easy_reward_pct: int = 60
    mordoboi_challenge_expiry_hours: int = 24
    mordoboi_move_timeout_hours: int = 12
    mordoboi_live_move_seconds: int = 30
    mordoboi_max_auto_moves: int = 3
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
    chemistry_enabled: bool = False
    chemistry_link_strong: int = 2
    chemistry_link_medium: int = 1
    chemistry_threshold_1: int = 1
    chemistry_threshold_2: int = 2
    chemistry_threshold_3: int = 4
    chemistry_player_max: int = 3
    chemistry_player_floor: int = 0
    chemistry_rating_per_point: int = 1
    chemistry_off_position_penalty: int = 0
    chemistry_coach_country_points: int = 1
    chemistry_stadium_club_points: int = 1
    card_stars_enabled: bool = False
    card_stars_max: int = 3
    card_star_dupes_per_level: dict[str, list[int]] = {}
    card_star_coin_cost: dict[str, list[int]] = {}
    card_star_rating_per_star: int = 1
    card_star_bonus_cap: int = 6
    path_enabled: bool = True
    path_title: str = "Академия"
    path_xp_base: int = 75
    path_xp_step: int = 10
    path_start_rating: int = 60
    path_rating_per_level: int = 1
    path_xp_match: int = 10
    path_xp_win: int = 10
    path_xp_draw: int = 3
    path_xp_goal: int = 5
    path_xp_assist: int = 3
    path_daily_free_arena: int = 10
    path_daily_career: int = 2
    path_daily_ptour: int = 3
    path_coin_attempt_prices: list[int] = []
    path_stars_attempt_prices: list[int] = []
    path_talent_cap: int = 8
    match_max_path_cards: int = 1
    tactico_max_path_cards: int = 1
    stratego_max_path_cards: int = 1
    path_prestige_dupes: list[int] = []
    path_prestige_coins: list[int] = []
    path_prestige_names: list[str] = []
    path_prestige_rewards: list[dict] = []
    path_prestige_xp_pct: int = 5
    path_prestige_xp_cap_pct: int = 15
    path_prestige_free_attempts: int = 1
    path_prestige_sell_pct: int = 50
    path_prestige_other_ratio: int = 5
    academy_enabled: bool = True
    academy_buildings: dict = {}
    academy_stars_per_hour: int = 2
    academy_scout_report: dict = {}
    club_base_enabled: bool = True
    club_base_buildings: dict = {}
    club_base_caps: dict = {}
    club_base_stars_per_hour: int = 2
    club_base_income_max_days: int = 3
    club_base_art: dict = {}
    club_base_cosmetics: list[dict] = []
    calendar_catchup_coins: int = 150
    calendar_catchup_stars: int = 10
    calendar_catchup_max_per_month: int = 5
    club_pass_enabled: bool = False
    club_pass_stars: int = 199
    club_pass_daily_coins: int = 300
    club_pass_daily_pack_id: Optional[int] = None
    club_pass_extra_rewarded_attempts: int = 2
    club_pass_bonus_coins: int = 2000
    club_pass_bonus_pack_id: Optional[int] = None
    club_pass_bonus_card_rarity: Optional[str] = None
    club_pass_season_xp_bonus_pct: int = 50
    club_pass_free_catchups: int = 3
    club_pass_status: int = 50
    season_premium_status: int = 30
    club_pass_frame_cosmetic_id: Optional[int] = None
    club_pass_badge_id: Optional[int] = None
    club_pass_ad_free: bool = True
    season_pass_enabled: bool = False
    season_xp_per_game: int = 10
    season_xp_per_daily_claim: int = 25
    starter_offer_enabled: bool = False
    starter_offer_hours: int = 48
    starter_offer_stars: int = 50
    starter_offer_coins: int = 1000
    starter_offer_pack_id: Optional[int] = None
    starter_offer_cosmetic_id: Optional[int] = None
    artifacts_enabled: bool = False
    artifact_slots: int = 3
    artifact_max_opp_pct: int = 5
    artifact_max_stat: int = 6
    club_emblems_enabled: bool = True
    club_donation_enabled: bool = False
    club_donation_coins_per_star: int = 15
    club_donation_star_options: list[int] = []
    club_sponsor_silver_stars: int = 250
    club_sponsor_gold_stars: int = 1000
    club_card_market_enabled: bool = True
    club_card_sell_pct: int = 100
    club_card_exchange_count: int = 5
    club_card_exchange_pack_id: Optional[int] = None
    club_announcement_cooldown_minutes: int = 60
    club_quests_enabled: bool = True
    club_league_season_weeks: int = 4
    club_league_promote_count: int = 3
    club_league_relegate_count: int = 3
    club_league_division_reward_pct: list[int] = []
    club_war_enabled: bool = True
    club_war_start_weekday: int = 4
    club_war_start_hour: int = 18
    club_war_duration_hours: int = 48
    club_war_min_members: int = 3
    club_war_member_cap: int = 100
    club_war_win_budget: int = 3000
    club_war_draw_budget: int = 1500
    club_war_loss_budget: int = 500
    club_war_win_member_coins: int = 200
    weekly_cup_enabled: bool = True
    weekly_cup_games: list[str] = []
    weekly_cup_best_of: int = 5
    weekly_cup_prizes: list[int] = []
    match_day_enabled: bool = False
    match_day_exact_coins: int = 1000
    match_day_diff_coins: int = 400
    match_day_outcome_coins: int = 200
    match_day_auto_enabled: bool = False
    match_day_leagues: list[int] = []
    club_raid_enabled: bool = True
    club_raid_hp_per_member: int = 3000
    club_raid_attacks_per_day: int = 3
    club_raid_shots: int = 6
    club_raid_damage_per_goal: int = 100
    club_raid_reward_coins: int = 1000
    club_raid_reward_pack_id: Optional[int] = None
    club_raid_reward_budget: int = 2000
    trade_send_min_account_age_days: int = 3
    trade_send_min_active_days: int = 2
    trade_daily_coins_receive_cap: int = 3000
    trade_coin_tax_pct: int = 0
    trade_coins_enabled: bool = False
    trade_cards_both_sides: bool = True
    trade_finder_max_wants: int = 10
    trade_finder_max_gives: int = 20
    trade_finder_active_days: int = 7
    trade_finder_notify_hours: int = 24
    trade_suspicious_young_days: int = 14
    trade_suspicious_min_donors: int = 3
    stake_max_coins: int = 500
    stake_pair_daily_limit: int = 2
    stake_daily_profit_cap: int = 2000
    equipment_enabled: bool = False
    equipment_max_rating: int = 3
    equipment_max_pp: int = 8
    equipment_max_chemistry: int = 1
    equipment_max_talisman_pct: int = 15
    pity_packs: int = 0
    bulk10_discount_pct: int = 0
    first_coin_purchase_bonus_pct: int = 0


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
    arena_style_matchup_bonus_pct: Optional[int] = Field(default=None, ge=0, le=50)
    arena_share_exponent: Optional[float] = Field(default=None, ge=0, le=5)
    arena_shot_exponent: Optional[float] = Field(default=None, ge=0, le=5)
    arena_edge_rating_per_10pct: Optional[float] = Field(default=None, ge=0, le=10)
    arena_edge_rating_max: Optional[int] = Field(default=None, ge=0, le=40)
    arena_formation_effect_pct: Optional[int] = Field(default=None, ge=0, le=300)
    arena_points_k: Optional[int] = Field(default=None, ge=1, le=200)
    arena_points_scale: Optional[int] = Field(default=None, ge=50, le=2000)
    arena_shield_matches: Optional[int] = Field(default=None, ge=0, le=20)
    arena_matchmaking_window: Optional[int] = Field(default=None, ge=0, le=5000)
    arena_division_min_points: Optional[list[int]] = Field(default=None, min_length=1, max_length=30)
    arena_division_reward_coins: Optional[list[int]] = Field(default=None, min_length=1, max_length=30)
    arena_division_coin_pct: Optional[list[int]] = Field(default=None, min_length=1, max_length=30)
    equipment_enabled: Optional[bool] = None
    equipment_max_rating: Optional[int] = Field(default=None, ge=0, le=10)
    equipment_max_pp: Optional[int] = Field(default=None, ge=0, le=30)
    equipment_max_chemistry: Optional[int] = Field(default=None, ge=0, le=3)
    equipment_max_talisman_pct: Optional[int] = Field(default=None, ge=0, le=100)

    @field_validator("arena_division_min_points")
    @classmethod
    def _arena_thresholds(cls, value):
        if value is None:
            return value
        if value[0] != 0 or any(b <= a for a, b in zip(value, value[1:])):
            raise ValueError("Пороги дивизионов: первый 0, дальше строго по возрастанию")
        return value

    @field_validator("arena_division_reward_coins", "arena_division_coin_pct")
    @classmethod
    def _arena_division_values(cls, value):
        if value is not None and any(int(v) < 0 for v in value):
            raise ValueError("Значения по дивизионам не могут быть отрицательными")
        return value
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
    trades_enabled: Optional[bool] = None
    leagues_enabled: Optional[bool] = None
    free_pack_interval_hours: Optional[int] = Field(default=None, ge=1)
    bot_daily_digest_enabled: Optional[bool] = None
    bot_daily_digest_hour: Optional[int] = Field(default=None, ge=0, le=23)
    shop_daily_offer_enabled: Optional[bool] = None
    shop_daily_offer_discount_pct: Optional[int] = Field(default=None, ge=1, le=90)
    # 0 = rotate through active coin packs by date (stored as NULL).
    shop_daily_offer_pack_id: Optional[int] = Field(default=None, ge=0)
    club_league_enabled: Optional[bool] = None
    club_league_points_game: Optional[int] = Field(default=None, ge=0, le=1000)
    club_league_points_pack: Optional[int] = Field(default=None, ge=0, le=1000)
    club_league_points_task: Optional[int] = Field(default=None, ge=0, le=1000)
    club_league_member_weekly_cap: Optional[int] = Field(default=None, ge=1)
    # Club budget coins by weekly place (index 0 = 1st); places past the list get nothing.
    club_league_rewards: Optional[list[Annotated[int, Field(ge=0)]]] = Field(default=None, min_length=1, max_length=50)
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
    career_yellow_chance_pct: Optional[int] = Field(default=None, ge=0, le=50)
    career_red_chance_pct: Optional[int] = Field(default=None, ge=0, le=20)
    career_yellows_for_ban: Optional[int] = Field(default=None, ge=1, le=10)
    career_form_max: Optional[int] = Field(default=None, ge=0, le=5)
    career_reminders_enabled: Optional[bool] = None
    career_tactics_tuning: Optional[dict] = None
    career_familiarity_axis_keep_pct: Optional[int] = Field(default=None, ge=0, le=100)
    career_squad_size: Optional[int] = Field(default=None, ge=16, le=30)
    career_ambition_bonus_pct: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    career_ambition_rep_success: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    career_ambition_rep_fail: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    career_rep_title: Optional[int] = Field(default=None, ge=0, le=500)
    career_rep_promotion: Optional[int] = Field(default=None, ge=0, le=500)
    career_rep_relegation: Optional[int] = Field(default=None, ge=-500, le=0)
    career_rep_levels: Optional[list[int]] = Field(default=None, min_length=2, max_length=10)
    career_cup_enabled: Optional[bool] = None
    career_cup_rewards: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    career_rep_cup: Optional[int] = Field(default=None, ge=0, le=500)
    career_offseason_auto: Optional[bool] = None
    career_inactive_days: Optional[int] = Field(default=None, ge=1, le=60)
    career_core_min: Optional[int] = Field(default=None, ge=0, le=30)
    career_core_keep_pct: Optional[int] = Field(default=None, ge=0, le=100)
    career_camp_physical_pct: Optional[int] = Field(default=None, ge=0, le=100)
    career_camp_physical_rounds: Optional[int] = Field(default=None, ge=0, le=14)
    career_camp_tactical_tenths: Optional[int] = Field(default=None, ge=0, le=150)
    career_tenure_minutes_per_point: Optional[int] = Field(default=None, ge=90, le=100000)
    career_tenure_max: Optional[int] = Field(default=None, ge=0, le=10)
    career_division_club_count: Optional[int] = Field(default=None, ge=7, le=40)
    career_live_enabled: Optional[bool] = None
    career_halftime_minutes: Optional[int] = Field(default=None, ge=3, le=120)
    career_achievement_reward: Optional[int] = Field(default=None, ge=0, le=100000)
    career_digest_enabled: Optional[bool] = None
    career_familiarity_step_tenths: Optional[int] = Field(default=None, ge=0, le=50)
    career_familiarity_max_tenths: Optional[int] = Field(default=None, ge=0, le=150)
    career_familiarity_keep_pct: Optional[int] = Field(default=None, ge=0, le=100)
    career_max_plan_rules: Optional[int] = Field(default=None, ge=0, le=5)
    career_max_substitutions: Optional[int] = Field(default=None, ge=0, le=5)
    career_bot_counter_chance_pct: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    career_division_count: Optional[int] = Field(default=None, ge=1, le=10)
    career_division_promote: Optional[int] = Field(default=None, ge=0, le=4)
    career_division_relegate: Optional[int] = Field(default=None, ge=0, le=4)
    career_division_rating_offset: Optional[list[int]] = Field(default=None, min_length=1, max_length=10)
    career_division_reward_pct: Optional[list[int]] = Field(default=None, min_length=1, max_length=10)
    career_division_bot_level: Optional[list[str]] = Field(default=None, min_length=1, max_length=10)
    my_player_enabled: Optional[bool] = None
    my_player_xp_per_reward: Optional[int] = Field(default=None, ge=0, le=1000)
    my_player_xp_daily_cap: Optional[int] = Field(default=None, ge=0, le=100000)
    my_player_xp_career_match: Optional[int] = Field(default=None, ge=0, le=1000)
    my_player_xp_level_base: Optional[int] = Field(default=None, ge=1, le=100000)
    my_player_xp_level_step: Optional[int] = Field(default=None, ge=0, le=10000)
    my_player_points_per_level: Optional[int] = Field(default=None, ge=1, le=20)
    my_player_rating_cap: Optional[int] = Field(default=None, ge=50, le=99)
    # [silver, gold, legend] rating thresholds.
    my_player_tier_thresholds: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    my_player_training_xp_base: Optional[int] = Field(default=None, ge=0, le=10000)
    my_player_training_xp_per_hit: Optional[int] = Field(default=None, ge=0, le=10000)
    my_player_cosmetic_prices: Optional[dict[str, int]] = None
    my_player_extra_trainings_max: Optional[int] = Field(default=None, ge=0, le=20)
    my_player_extra_training_coins: Optional[int] = Field(default=None, ge=0)
    my_player_extra_training_stars: Optional[int] = Field(default=None, ge=0, le=10000)
    my_player_streak_days: Optional[int] = Field(default=None, ge=1, le=60)
    my_player_streak_tokens: Optional[int] = Field(default=None, ge=0, le=100)
    my_player_freshness_per_match: Optional[int] = Field(default=None, ge=0, le=100)
    my_player_freshness_regen_per_hour: Optional[int] = Field(default=None, ge=0, le=100)
    my_player_freshness_training: Optional[int] = Field(default=None, ge=0, le=100)
    my_player_fatigue_max_penalty: Optional[int] = Field(default=None, ge=0, le=30)
    my_player_duels_per_day: Optional[int] = Field(default=None, ge=0, le=100)
    my_player_duel_reward_win: Optional[int] = Field(default=None, ge=0)
    my_player_duel_reward_draw: Optional[int] = Field(default=None, ge=0)
    my_player_duel_xp: Optional[int] = Field(default=None, ge=0, le=1000)
    my_player_role_change_coins: Optional[int] = Field(default=None, ge=0)
    my_player_role_change_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    my_player_cosmetic_stars_prices: Optional[dict[str, int]] = None
    player_career_level_ratings: Optional[list[int]] = Field(default=None, min_length=5, max_length=5)
    player_career_level_salary: Optional[list[int]] = Field(default=None, min_length=5, max_length=5)
    player_career_level_prestige: Optional[list[int]] = Field(default=None, min_length=5, max_length=5)
    player_career_star_prestige: Optional[list[int]] = Field(default=None, min_length=5, max_length=5)
    player_career_star_salary_pct: Optional[int] = Field(default=None, ge=0, le=500)
    player_career_prestige_salary_cap: Optional[int] = Field(default=None, ge=0, le=500)
    player_career_contract_seasons: Optional[int] = Field(default=None, ge=1, le=10)
    player_career_free_agent_level: Optional[int] = Field(default=None, ge=1, le=5)
    player_career_offers_max: Optional[int] = Field(default=None, ge=0, le=10)
    player_career_haggle_base: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_haggle_raise_penalty: Optional[int] = Field(default=None, ge=0, le=10)
    player_career_haggle_repeat_penalty: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_cl_places: Optional[int] = Field(default=None, ge=0, le=8)
    player_career_cl_rewards: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    player_career_cl_prestige: Optional[int] = Field(default=None, ge=0, le=10000)
    player_career_national_prestige: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_national_rewards: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    player_career_national_win_prestige: Optional[int] = Field(default=None, ge=0, le=10000)
    player_career_golden_ball_min_matches: Optional[int] = Field(default=None, ge=1, le=200)
    player_career_golden_ball_coins: Optional[int] = Field(default=None, ge=0)
    player_career_golden_ball_prestige: Optional[int] = Field(default=None, ge=0, le=10000)
    player_career_moments: Optional[int] = Field(default=None, ge=0, le=5)
    player_career_moment_hit_pct: Optional[int] = Field(default=None, ge=0, le=60)
    player_career_moment_window_hours: Optional[int] = Field(default=None, ge=1, le=48)
    player_career_bench_gap: Optional[int] = Field(default=None, ge=0, le=30)
    player_career_bench_play_pct: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_trust_starter: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_trust_captain: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_captain_salary_pct: Optional[int] = Field(default=None, ge=0, le=200)
    player_career_injury_freshness: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_injury_max_pct: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_heal_coins: Optional[int] = Field(default=None, ge=0, le=1000000)
    player_career_heal_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_refresh_coins: Optional[int] = Field(default=None, ge=0, le=1000000)
    player_career_refresh_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_event_every: Optional[int] = Field(default=None, ge=1, le=14)
    player_career_event_coins: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_event_prestige: Optional[int] = Field(default=None, ge=0, le=1000)
    player_career_derby_multiplier: Optional[int] = Field(default=None, ge=1, le=10)
    player_career_pro_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_pro_days: Optional[int] = Field(default=None, ge=1, le=365)
    player_career_pro_xp_pct: Optional[int] = Field(default=None, ge=0, le=500)
    player_career_agent_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_agent_haggle_bonus: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_save_offer_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_fast_season_enabled: Optional[bool] = None
    player_career_fast_season_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_fast_round_minutes: Optional[int] = Field(default=None, ge=15, le=1440)
    player_career_chest_coins_min: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_chest_coins_max: Optional[int] = Field(default=None, ge=0, le=100000)
    player_career_chest_token_pct: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_weekly_goals: Optional[int] = Field(default=None, ge=1, le=200)
    player_career_weekly_matches: Optional[int] = Field(default=None, ge=1, le=200)
    player_career_weekly_rating_x10: Optional[int] = Field(default=None, ge=10, le=100)
    player_career_weekly_coins: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    player_career_friends_rewards: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    manager_enabled: Optional[bool] = None
    manager_found_cost: Optional[int] = Field(default=None, ge=0, le=1000000)
    manager_min_level: Optional[int] = Field(default=None, ge=1, le=500)
    manager_max_live: Optional[int] = Field(default=None, ge=0, le=11)
    manager_squad_max: Optional[int] = Field(default=None, ge=11, le=40)
    manager_league_size: Optional[int] = Field(default=None, ge=4, le=20)
    manager_divisions: Optional[int] = Field(default=None, ge=1, le=12)
    manager_promote: Optional[int] = Field(default=None, ge=1, le=4)
    manager_preseason_hours: Optional[int] = Field(default=None, ge=1, le=150)
    manager_style_edge_pct: Optional[int] = Field(default=None, ge=0, le=50)
    ptour_style_edge_pct: Optional[int] = Field(default=None, ge=0, le=50)
    ptour_formation_effect_pct: Optional[int] = Field(default=None, ge=0, le=300)
    manager_formation_effect_pct: Optional[int] = Field(default=None, ge=0, le=300)
    manager_wage_pct: Optional[int] = Field(default=None, ge=0, le=100)
    manager_loan_fee_pct: Optional[int] = Field(default=None, ge=0, le=100)
    manager_sell_back_pct: Optional[int] = Field(default=None, ge=0, le=100)
    manager_live_wage_max: Optional[int] = Field(default=None, ge=0, le=1000000)
    manager_wage_eur_per_coin: Optional[int] = Field(default=None, ge=0, le=1000000)
    manager_form_bonus_pct: Optional[int] = Field(default=None, ge=0, le=100)
    manager_form_bonus_cap: Optional[int] = Field(default=None, ge=0, le=500)
    manager_income_win: Optional[int] = Field(default=None, ge=0, le=100000000)
    manager_income_draw: Optional[int] = Field(default=None, ge=0, le=100000000)
    manager_income_loss: Optional[int] = Field(default=None, ge=0, le=100000000)
    manager_ticket_eur_per_level: Optional[int] = Field(default=None, ge=0, le=10000000)
    manager_sponsor_eur_per_level: Optional[int] = Field(default=None, ge=0, le=100000000)
    manager_merch_eur_per_level: Optional[int] = Field(default=None, ge=0, le=100000000)
    manager_budget_per_base_level: Optional[int] = Field(default=None, ge=0, le=100000000)
    manager_base_bonus_cap_pct: Optional[int] = Field(default=None, ge=0, le=1000)
    manager_promotion_bonus_pct: Optional[int] = Field(default=None, ge=0, le=500)
    manager_parachute_pct: Optional[int] = Field(default=None, ge=0, le=100)
    manager_match_xp: Optional[int] = Field(default=None, ge=0, le=10000)
    manager_freshness_cost: Optional[int] = Field(default=None, ge=0, le=100)
    manager_merch_cap_eur: Optional[int] = Field(default=None, ge=0, le=2000000000)
    manager_pro_stars: Optional[int] = Field(default=None, ge=0, le=100000)
    manager_pro_days: Optional[int] = Field(default=None, ge=1, le=365)
    manager_value_ratings: Optional[list[int]] = Field(default=None, min_length=2, max_length=30)
    manager_value_eur: Optional[list[int]] = Field(default=None, min_length=2, max_length=30)
    manager_division_budget: Optional[list[int]] = Field(default=None, min_length=1, max_length=12)
    manager_division_income_pct: Optional[list[int]] = Field(default=None, min_length=1, max_length=12)
    manager_division_wage_pct: Optional[list[int]] = Field(default=None, min_length=1, max_length=12)
    manager_division_rating: Optional[list[int]] = Field(default=None, min_length=1, max_length=12)
    manager_place_rewards: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    manager_place_budget: Optional[list[int]] = Field(default=None, min_length=3, max_length=3)
    manager_slots: Optional[list[str]] = Field(default=None, min_length=1, max_length=8)
    manager_cosmetics: Optional[list[dict]] = Field(default=None, max_length=200)
    manager_merch: Optional[list[dict]] = Field(default=None, max_length=20)
    player_career_objective_coins: Optional[int] = Field(default=None, ge=0)
    player_career_objective_rep: Optional[int] = Field(default=None, ge=0, le=1000)
    player_career_enabled: Optional[bool] = None
    player_career_rating_margin: Optional[int] = Field(default=None, ge=0, le=30)
    player_career_rep_per_goal: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_rep_per_assist: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_rep_per_win: Optional[int] = Field(default=None, ge=0, le=100)
    player_career_rep_title: Optional[int] = Field(default=None, ge=0, le=1000)
    player_career_match_reward_win: Optional[int] = Field(default=None, ge=0)
    player_career_match_reward_draw: Optional[int] = Field(default=None, ge=0)
    player_career_goal_reward: Optional[int] = Field(default=None, ge=0)
    player_career_match_xp: Optional[int] = Field(default=None, ge=0, le=1000)
    # 8 places.
    player_career_place_rewards: Optional[list[int]] = Field(default=None, min_length=8, max_length=8)
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
    stratego_board_size: Optional[int] = Field(default=None, ge=5, le=10)
    stratego_max_legendary_cards: Optional[int] = Field(default=None, ge=0, le=20)
    stratego_max_diamond_cards: Optional[int] = Field(default=None, ge=0, le=20)
    stratego_min_rare_cards: Optional[int] = Field(default=None, ge=0, le=20)
    stratego_min_common_cards: Optional[int] = Field(default=None, ge=0, le=20)
    stratego_my_player_xp: Optional[int] = Field(default=None, ge=0, le=1000)
    stratego_tackler_max_rarity: Optional[Literal["common", "rare", "epic", "legendary", "diamond"]] = None
    stratego_provocateur_max_rarity: Optional[Literal["common", "rare", "epic", "legendary", "diamond"]] = None
    stratego_speedster_max_rarity: Optional[Literal["common", "rare", "epic", "legendary", "diamond"]] = None
    stratego_bot_easy_reward_pct: Optional[int] = Field(default=None, ge=0, le=200)
    stratego_live_move_seconds: Optional[int] = Field(default=None, ge=15, le=3600)
    stratego_skill_bonus_per_level: Optional[int] = Field(default=None, ge=0, le=20)
    stratego_puzzle_reward: Optional[int] = Field(default=None, ge=0)
    stratego_tackler_count: Optional[int] = Field(default=None, ge=1, le=6)
    stratego_speedster_count: Optional[int] = Field(default=None, ge=0, le=6)
    stratego_wall_count: Optional[int] = Field(default=None, ge=0, le=4)
    stratego_regular_count: Optional[int] = Field(default=None, ge=0, le=12)
    stratego_move_limit: Optional[int] = Field(default=None, ge=4, le=400)
    stratego_challenge_expiry_hours: Optional[int] = Field(default=None, ge=1)
    stratego_move_timeout_hours: Optional[int] = Field(default=None, ge=1)
    stratego_max_auto_moves: Optional[int] = Field(default=None, ge=0, le=50)
    stratego_reward_win: Optional[int] = Field(default=None, ge=0)
    stratego_reward_draw: Optional[int] = Field(default=None, ge=0)
    stratego_reward_loss: Optional[int] = Field(default=None, ge=0)
    stratego_daily_limit: Optional[int] = Field(default=None, ge=0)
    magnate_start_money: Optional[int] = Field(default=None, ge=100, le=100000)
    magnate_pass_start_bonus: Optional[int] = Field(default=None, ge=0, le=10000)
    magnate_jail_fine: Optional[int] = Field(default=None, ge=0, le=10000)
    magnate_max_jail_turns: Optional[int] = Field(default=None, ge=1, le=5)
    magnate_fine_amount: Optional[int] = Field(default=None, ge=0, le=10000)
    magnate_building_sell_pct: Optional[int] = Field(default=None, ge=0, le=100)
    magnate_max_rounds: Optional[int] = Field(default=None, ge=3, le=60)
    magnate_time_limit_minutes: Optional[int] = Field(default=None, ge=5, le=120)
    magnate_turn_seconds: Optional[int] = Field(default=None, ge=10, le=300)
    magnate_max_missed_turns: Optional[int] = Field(default=None, ge=1, le=10)
    magnate_lobby_wait_seconds: Optional[int] = Field(default=None, ge=10, le=600)
    magnate_room_wait_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    magnate_bot_buy_reserve: Optional[int] = Field(default=None, ge=0)
    magnate_bot_build_reserve: Optional[int] = Field(default=None, ge=0)
    magnate_bot_reward_pct: Optional[int] = Field(default=None, ge=0, le=100)
    magnate_daily_limit: Optional[int] = Field(default=None, ge=0)
    magnate_place_rewards: Optional[list[Annotated[int, Field(ge=0)]]] = Field(default=None, min_length=1, max_length=4)
    magnate_stadium_rents: Optional[list[Annotated[int, Field(ge=0)]]] = Field(default=None, min_length=4, max_length=4)
    # Validated by magnate_engine.validate_board / validate_cards in the router.
    magnate_board: Optional[dict] = None
    magnate_cards: Optional[dict] = None
    match_max_diamond_cards: Optional[int] = Field(default=None, ge=0, le=11)
    diamond_rating_cap: Optional[int] = Field(default=None, ge=1, le=99)
    diamond_rating_cap_enabled: Optional[bool] = None
    wheel_free_spins_per_day: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_coins: Optional[int] = Field(default=None, ge=0)
    wheel_spin_cost_stars: Optional[int] = Field(default=None, ge=0)
    wheel_duplicate_badge_coins: Optional[int] = Field(default=None, ge=0)
    blackjack_enabled: Optional[bool] = None
    blackjack_free_per_day: Optional[int] = Field(default=None, ge=0, le=20)
    blackjack_stars_cost: Optional[int] = Field(default=None, ge=1, le=10000)
    blackjack_paid_daily_limit: Optional[int] = Field(default=None, ge=0, le=100)
    blackjack_consolation_coins: Optional[int] = Field(default=None, ge=0)
    mordoboi_enabled: Optional[bool] = None
    mordoboi_rounds: Optional[int] = Field(default=None, ge=1, le=12)
    mordoboi_exchanges_per_round: Optional[int] = Field(default=None, ge=1, le=10)
    mordoboi_base_hp: Optional[int] = Field(default=None, ge=20, le=1000)
    mordoboi_reward_win: Optional[int] = Field(default=None, ge=0)
    mordoboi_reward_draw: Optional[int] = Field(default=None, ge=0)
    mordoboi_reward_loss: Optional[int] = Field(default=None, ge=0)
    mordoboi_reward_ko_bonus: Optional[int] = Field(default=None, ge=0)
    mordoboi_daily_limit: Optional[int] = Field(default=None, ge=0)
    mordoboi_bot_easy_reward_pct: Optional[int] = Field(default=None, ge=0, le=200)
    mordoboi_challenge_expiry_hours: Optional[int] = Field(default=None, ge=1)
    mordoboi_move_timeout_hours: Optional[int] = Field(default=None, ge=1)
    mordoboi_live_move_seconds: Optional[int] = Field(default=None, ge=10, le=3600)
    mordoboi_max_auto_moves: Optional[int] = Field(default=None, ge=0, le=50)
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
    chemistry_enabled: Optional[bool] = None
    chemistry_link_strong: Optional[int] = Field(default=None, ge=0, le=10)
    chemistry_link_medium: Optional[int] = Field(default=None, ge=0, le=10)
    chemistry_threshold_1: Optional[int] = Field(default=None, ge=0, le=40)
    chemistry_threshold_2: Optional[int] = Field(default=None, ge=0, le=40)
    chemistry_threshold_3: Optional[int] = Field(default=None, ge=0, le=40)
    chemistry_player_max: Optional[int] = Field(default=None, ge=0, le=3)
    chemistry_player_floor: Optional[int] = Field(default=None, ge=0, le=3)
    chemistry_rating_per_point: Optional[int] = Field(default=None, ge=0, le=10)
    chemistry_off_position_penalty: Optional[int] = Field(default=None, ge=0, le=20)
    chemistry_coach_country_points: Optional[int] = Field(default=None, ge=0, le=3)
    chemistry_stadium_club_points: Optional[int] = Field(default=None, ge=0, le=3)
    card_stars_enabled: Optional[bool] = None
    card_stars_max: Optional[int] = Field(default=None, ge=0, le=5)
    card_star_dupes_per_level: Optional[dict[str, list[int]]] = None
    card_star_coin_cost: Optional[dict[str, list[int]]] = None
    card_star_rating_per_star: Optional[int] = Field(default=None, ge=0, le=10)
    card_star_bonus_cap: Optional[int] = Field(default=None, ge=0, le=30)
    path_enabled: Optional[bool] = None
    path_title: Optional[str] = Field(default=None, min_length=1, max_length=64)
    path_xp_base: Optional[int] = Field(default=None, ge=1, le=10000)
    path_xp_step: Optional[int] = Field(default=None, ge=0, le=10000)
    path_start_rating: Optional[int] = Field(default=None, ge=1, le=99)
    path_rating_per_level: Optional[int] = Field(default=None, ge=1, le=5)
    path_xp_match: Optional[int] = Field(default=None, ge=0, le=1000)
    path_xp_win: Optional[int] = Field(default=None, ge=0, le=1000)
    path_xp_draw: Optional[int] = Field(default=None, ge=0, le=1000)
    path_xp_goal: Optional[int] = Field(default=None, ge=0, le=1000)
    path_xp_assist: Optional[int] = Field(default=None, ge=0, le=1000)
    path_daily_free_arena: Optional[int] = Field(default=None, ge=0, le=100)
    path_daily_career: Optional[int] = Field(default=None, ge=0, le=100)
    path_daily_ptour: Optional[int] = Field(default=None, ge=0, le=100)
    path_coin_attempt_prices: Optional[list[int]] = Field(default=None, max_length=20)
    path_stars_attempt_prices: Optional[list[int]] = Field(default=None, max_length=20)
    path_talent_cap: Optional[int] = Field(default=None, ge=0, le=20)
    match_max_path_cards: Optional[int] = Field(default=None, ge=0, le=11)
    tactico_max_path_cards: Optional[int] = Field(default=None, ge=0, le=11)
    stratego_max_path_cards: Optional[int] = Field(default=None, ge=0, le=20)
    path_prestige_dupes: Optional[list[int]] = Field(default=None, max_length=10)
    path_prestige_coins: Optional[list[int]] = Field(default=None, max_length=10)
    path_prestige_names: Optional[list[str]] = Field(default=None, max_length=10)
    path_prestige_rewards: Optional[list[dict[str, int]]] = Field(default=None, max_length=10)
    path_prestige_xp_pct: Optional[int] = Field(default=None, ge=0, le=100)
    path_prestige_xp_cap_pct: Optional[int] = Field(default=None, ge=0, le=200)
    path_prestige_free_attempts: Optional[int] = Field(default=None, ge=0, le=20)
    path_prestige_sell_pct: Optional[int] = Field(default=None, ge=0, le=1000)
    path_prestige_other_ratio: Optional[int] = Field(default=None, ge=1, le=50)
    academy_enabled: Optional[bool] = None
    academy_buildings: Optional[dict[str, dict[str, list[int]]]] = None
    academy_stars_per_hour: Optional[int] = Field(default=None, ge=1, le=100)
    academy_scout_report: Optional[dict[str, list[int]]] = None
    club_base_enabled: Optional[bool] = None
    club_base_buildings: Optional[dict[str, dict[str, list[int]]]] = None
    club_base_caps: Optional[dict[str, int]] = None
    club_base_stars_per_hour: Optional[int] = Field(default=None, ge=1, le=100)
    club_base_income_max_days: Optional[int] = Field(default=None, ge=1, le=30)
    club_base_cosmetics: Optional[list[dict]] = Field(default=None, max_length=100)
    trade_send_min_account_age_days: Optional[int] = Field(default=None, ge=0, le=365)
    trade_send_min_active_days: Optional[int] = Field(default=None, ge=0, le=365)
    trade_daily_coins_receive_cap: Optional[int] = Field(default=None, ge=0)
    trade_coin_tax_pct: Optional[int] = Field(default=None, ge=0, le=90)
    trade_coins_enabled: Optional[bool] = None
    trade_cards_both_sides: Optional[bool] = None
    trade_finder_max_wants: Optional[int] = Field(default=None, ge=0, le=100)
    trade_finder_max_gives: Optional[int] = Field(default=None, ge=0, le=100)
    trade_finder_active_days: Optional[int] = Field(default=None, ge=1, le=90)
    trade_finder_notify_hours: Optional[int] = Field(default=None, ge=0, le=720)
    trade_suspicious_young_days: Optional[int] = Field(default=None, ge=1, le=365)
    trade_suspicious_min_donors: Optional[int] = Field(default=None, ge=2, le=100)
    stake_max_coins: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    stake_pair_daily_limit: Optional[int] = Field(default=None, ge=0, le=100)
    stake_daily_profit_cap: Optional[int] = Field(default=None, ge=0)
    pity_packs: Optional[int] = Field(default=None, ge=0, le=1000)
    bulk10_discount_pct: Optional[int] = Field(default=None, ge=0, le=50)
    first_coin_purchase_bonus_pct: Optional[int] = Field(default=None, ge=0, le=300)

    @field_validator("path_prestige_dupes", "path_prestige_coins")
    @classmethod
    def _non_negative_tiers(cls, value):
        if value is not None and any(int(v) < 0 for v in value):
            raise ValueError("Значения по ступеням не могут быть отрицательными")
        return value

    @field_validator("path_coin_attempt_prices", "path_stars_attempt_prices")
    @classmethod
    def _positive_prices(cls, value):
        if value is not None and any(int(v) < 1 for v in value):
            raise ValueError("Цены попыток должны быть не меньше 1")
        return value

    @field_validator("card_star_dupes_per_level", "card_star_coin_cost")
    @classmethod
    def _star_levels_per_rarity(cls, value, info):
        # Diamond is deliberately not allowed: diamond cards have their own upgrade.
        if value is None:
            return value
        allowed = {"common", "rare", "epic", "legendary"}
        minimum = 1 if info.field_name == "card_star_dupes_per_level" else 0
        for rarity, levels in value.items():
            if rarity not in allowed:
                raise ValueError(f"unknown rarity '{rarity}' (allowed: {', '.join(sorted(allowed))})")
            if len(levels) > 5 or any(not minimum <= v <= 1_000_000 for v in levels):
                raise ValueError(f"{rarity}: up to 5 values, each {minimum}..1000000")
        return value

    calendar_catchup_coins: Optional[int] = Field(default=None, ge=0)
    calendar_catchup_stars: Optional[int] = Field(default=None, ge=0, le=10000)
    calendar_catchup_max_per_month: Optional[int] = Field(default=None, ge=0, le=31)
    club_pass_enabled: Optional[bool] = None
    club_pass_stars: Optional[int] = Field(default=None, ge=1, le=10000)
    club_pass_daily_coins: Optional[int] = Field(default=None, ge=0)
    club_pass_daily_pack_id: Optional[int] = Field(default=None, ge=0)
    club_pass_extra_rewarded_attempts: Optional[int] = Field(default=None, ge=0, le=20)
    club_pass_bonus_coins: Optional[int] = Field(default=None, ge=0)
    club_pass_bonus_pack_id: Optional[int] = Field(default=None, ge=0)
    club_pass_bonus_card_rarity: Optional[Literal["", "common", "rare", "epic", "legendary", "diamond"]] = None
    club_pass_season_xp_bonus_pct: Optional[int] = Field(default=None, ge=0, le=500)
    club_pass_free_catchups: Optional[int] = Field(default=None, ge=0, le=31)
    club_pass_status: Optional[int] = Field(default=None, ge=0, le=10000)
    season_premium_status: Optional[int] = Field(default=None, ge=0, le=10000)
    club_pass_frame_cosmetic_id: Optional[int] = Field(default=None, ge=0)
    club_pass_badge_id: Optional[int] = Field(default=None, ge=0)
    club_pass_ad_free: Optional[bool] = None
    season_pass_enabled: Optional[bool] = None
    season_xp_per_game: Optional[int] = Field(default=None, ge=0, le=10000)
    season_xp_per_daily_claim: Optional[int] = Field(default=None, ge=0, le=10000)
    starter_offer_enabled: Optional[bool] = None
    starter_offer_hours: Optional[int] = Field(default=None, ge=1, le=720)
    starter_offer_stars: Optional[int] = Field(default=None, ge=1, le=10000)
    starter_offer_coins: Optional[int] = Field(default=None, ge=0)
    starter_offer_pack_id: Optional[int] = Field(default=None, ge=0)
    starter_offer_cosmetic_id: Optional[int] = Field(default=None, ge=0)
    artifacts_enabled: Optional[bool] = None
    artifact_slots: Optional[int] = Field(default=None, ge=0, le=10)
    artifact_max_opp_pct: Optional[int] = Field(default=None, ge=0, le=50)
    artifact_max_stat: Optional[int] = Field(default=None, ge=0, le=50)
    club_emblems_enabled: Optional[bool] = None
    club_donation_enabled: Optional[bool] = None
    club_donation_coins_per_star: Optional[int] = Field(default=None, ge=1, le=10000)
    club_donation_star_options: Optional[list[Annotated[int, Field(ge=1, le=10000)]]] = Field(
        default=None, min_length=1, max_length=8,
    )
    club_sponsor_silver_stars: Optional[int] = Field(default=None, ge=1, le=1000000)
    club_sponsor_gold_stars: Optional[int] = Field(default=None, ge=1, le=1000000)
    club_card_market_enabled: Optional[bool] = None
    club_card_sell_pct: Optional[int] = Field(default=None, ge=0, le=1000)
    club_card_exchange_count: Optional[int] = Field(default=None, ge=2, le=20)
    club_card_exchange_pack_id: Optional[int] = Field(default=None, ge=0)
    club_announcement_cooldown_minutes: Optional[int] = Field(default=None, ge=0, le=10080)
    club_quests_enabled: Optional[bool] = None
    club_league_season_weeks: Optional[int] = Field(default=None, ge=1, le=52)
    club_league_promote_count: Optional[int] = Field(default=None, ge=0, le=50)
    club_league_relegate_count: Optional[int] = Field(default=None, ge=0, le=50)
    club_league_division_reward_pct: Optional[list[Annotated[int, Field(ge=0, le=1000)]]] = Field(
        default=None, min_length=3, max_length=3,
    )
    club_war_enabled: Optional[bool] = None
    club_war_start_weekday: Optional[int] = Field(default=None, ge=0, le=6)
    club_war_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    club_war_duration_hours: Optional[int] = Field(default=None, ge=1, le=168)
    club_war_min_members: Optional[int] = Field(default=None, ge=1, le=11)
    club_war_member_cap: Optional[int] = Field(default=None, ge=1, le=100000)
    club_war_win_budget: Optional[int] = Field(default=None, ge=0, le=10000000)
    club_war_draw_budget: Optional[int] = Field(default=None, ge=0, le=10000000)
    club_war_loss_budget: Optional[int] = Field(default=None, ge=0, le=10000000)
    club_war_win_member_coins: Optional[int] = Field(default=None, ge=0, le=10000000)
    weekly_cup_enabled: Optional[bool] = None
    weekly_cup_games: Optional[list[Literal["penalty", "free_kick", "memory", "saboteur", "pairs"]]] = Field(
        default=None, min_length=1, max_length=10,
    )
    weekly_cup_best_of: Optional[int] = Field(default=None, ge=1, le=50)
    weekly_cup_prizes: Optional[list[Annotated[int, Field(ge=0, le=10000000)]]] = Field(default=None, max_length=100)
    match_day_enabled: Optional[bool] = None
    match_day_exact_coins: Optional[int] = Field(default=None, ge=0, le=10000000)
    match_day_diff_coins: Optional[int] = Field(default=None, ge=0, le=10000000)
    match_day_outcome_coins: Optional[int] = Field(default=None, ge=0, le=10000000)
    match_day_auto_enabled: Optional[bool] = None
    match_day_leagues: Optional[list[Annotated[int, Field(ge=1, le=100000)]]] = Field(default=None, min_length=1, max_length=30)
    club_raid_enabled: Optional[bool] = None
    club_raid_hp_per_member: Optional[int] = Field(default=None, ge=1, le=10000000)
    club_raid_attacks_per_day: Optional[int] = Field(default=None, ge=1, le=50)
    club_raid_shots: Optional[int] = Field(default=None, ge=1, le=20)
    club_raid_damage_per_goal: Optional[int] = Field(default=None, ge=0, le=1000000)
    club_raid_reward_coins: Optional[int] = Field(default=None, ge=0, le=10000000)
    club_raid_reward_pack_id: Optional[int] = Field(default=None, ge=0)
    club_raid_reward_budget: Optional[int] = Field(default=None, ge=0, le=10000000)

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
    coins_in_circulation: int = 0
    inflow_outflow_ratio: Optional[float] = None
    positive_days: int = 0
    warning: Optional[str] = None
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
