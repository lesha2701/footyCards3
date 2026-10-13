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
    player_career_enabled: bool = True
    player_career_min_club_cards: int = 5
    player_career_rating_margin: int = 5
    player_career_rep_per_club_rating: int = 4
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
    player_career_enabled: Optional[bool] = None
    player_career_min_club_cards: Optional[int] = Field(default=None, ge=1, le=11)
    player_career_rating_margin: Optional[int] = Field(default=None, ge=0, le=30)
    player_career_rep_per_club_rating: Optional[int] = Field(default=None, ge=0, le=100)
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
