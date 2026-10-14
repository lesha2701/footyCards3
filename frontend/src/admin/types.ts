import type { Page, Pack, PackRarityProbability, Player, Rarity, TradeOffer, TradeStatus } from "@/types";

export interface DashboardChartPoint {
  date: string;
  count: number;
}

export interface RecentAdminAction {
  id: number;
  admin_id: number;
  action: string;
  entity_type: string;
  entity_id: number | null;
  created_at: string;
}

export interface Dashboard {
  total_users: number;
  active_users_7d: number;
  total_packs_opened: number;
  total_cards_issued: number;
  total_trades: number;
  coins_in_circulation: number;
  registrations_by_day: DashboardChartPoint[];
  pack_openings_by_day: DashboardChartPoint[];
  recent_actions: RecentAdminAction[];
}

export interface AdminUser {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  balance: number;
  is_admin: boolean;
  is_banned: boolean;
  game_rewards_blocked: boolean;
  is_trade_banned: boolean;
  arena_rating: number;
  created_at: string;
  last_seen_at: string | null;
}

export interface PackPreview {
  simulations: number;
  cards_per_open: number;
  rarity_distribution: { rarity: Rarity; count: number; percentage: number }[];
}

export interface StarsDonationSummary {
  total_stars: number;
  total_purchases: number;
}

export interface TopSupporter {
  user_id: number;
  user_telegram_id: number;
  user_username: string | null;
  user_display_name: string;
  total_stars: number;
  purchase_count: number;
}

export interface StarsPackPurchase {
  id: number;
  user_id: number;
  user_telegram_id: number;
  user_username: string | null;
  user_display_name: string;
  pack_id: number;
  pack_name: string;
  stars_amount: number;
  telegram_payment_charge_id: string | null;
  completed_at: string;
}

export interface AdminActionLog {
  id: number;
  admin_id: number;
  admin_username: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  ip_address: string | null;
  extra: string | null;
  created_at: string;
}

export interface GameConfig {
  club_creation_cost_coins: number;
  club_daily_reward_coins: number;
  club_tournament_cooldown_hours: number;
  club_form_window_matches: number;
  club_form_bonus_per_result: number;
  club_tournament_budget_place_1: number;
  club_tournament_budget_place_2: number;
  club_tournament_budget_place_3: number;
  club_tournament_budget_place_4: number;
  club_tournament_budget_place_5: number;
  club_tournament_budget_place_6: number;
  club_tournament_budget_place_7: number;
  club_tournament_budget_place_8: number;
  club_match_reward_win: number;
  club_match_reward_draw: number;
  club_match_reward_loss: number;
  club_member_match_reward_win: number;
  club_member_match_reward_draw: number;
  club_member_match_reward_loss: number;
  club_games_hourly_limit: number;
  club_game_daily_reward_limit: number;
  club_game_reward_cap: number;
  club_penalty_daily_reward_limit: number;
  club_penalty_reward_win: number;
  club_penalty_reward_loss: number;
  club_penalty_bot_miss_chance: number;
  club_position_match_daily_reward_limit: number;
  club_position_match_max_mistakes: number;
  club_position_match_reward_perfect: number;
  club_position_match_reward_min: number;
  club_position_match_penalty_per_mistake: number;
  fut_draft_entry_cost: number;
  fut_draft_weak_chance: number;
  fut_draft_normal_chance: number;
  fut_draft_strong_chance: number;
  fut_draft_top_chance: number;
  fut_draft_jackpot_chance: number;
  fut_draft_reward_win_0: number;
  fut_draft_reward_win_1: number;
  fut_draft_reward_win_2: number;
  fut_draft_reward_win_3: number;
  fut_draft_reward_win_4: number;
  fut_draft_club_bonus_per_extra: number;
  fut_draft_country_bonus_per_extra: number;
  fut_draft_round_bot_boost_pct: number;
  club_tactical_tackle_attempt_chance: number;
  club_tactical_injury_chance: number;
  club_training_boost_pct: number;
  club_training_uses_per_tournament: number;
  memory_daily_reward_limit: number;
  memory_reward_cap: number;
  suspicious_memory_score_threshold: number;
  match_reward_win: number;
  match_reward_draw: number;
  match_reward_loss: number;
  difficulty_easy_multiplier: number;
  difficulty_medium_multiplier: number;
  difficulty_hard_multiplier: number;
  suspicious_score_margin: number;
  match_shot_miss_chance_min: number;
  match_shot_miss_chance_max: number;
  match_defender_block_chance_min: number;
  match_defender_block_chance_max: number;
  match_shot_type_in_box_weight: number;
  match_shot_type_long_range_weight: number;
  match_shot_type_empty_net_weight: number;
  match_attack_shoot_miss_chance_min: number;
  match_attack_shoot_miss_chance_max: number;
  match_pass_fail_chance_min: number;
  match_pass_fail_chance_max: number;
  match_receiver_shot_miss_chance_min: number;
  match_receiver_shot_miss_chance_max: number;
  match_tackle_foul_chance_min: number;
  match_tackle_foul_chance_max: number;
  match_tackle_red_chance_min: number;
  match_tackle_red_chance_max: number;
  match_block_fail_chance_min: number;
  match_block_fail_chance_max: number;
  match_keeper_save_chance_min: number;
  match_keeper_save_chance_max: number;
  match_red_card_strength_penalty_pct: number;
  match_penalty_gk_rating_penalty: number;
  saboteur_line_base_reward: number;
  saboteur_line_growth: number;
  saboteur_max_steward_count: number;
  saboteur_daily_limit: number;
  penalty_reward_win: number;
  penalty_reward_draw: number;
  penalty_reward_loss: number;
  penalty_bot_miss_chance: number;
  penalty_daily_limit: number;
  free_kick_period_min_ms: number;
  free_kick_period_max_ms: number;
  free_kick_base_stake: number;
  free_kick_daily_limit: number;
  hourly_game_limit: number;
  matchmaking_enabled: boolean;
  wheel_enabled: boolean;
  leagues_enabled: boolean;
  free_pack_interval_hours: number;
  bot_daily_digest_enabled: boolean;
  bot_daily_digest_hour: number;
  shop_daily_offer_enabled: boolean;
  shop_daily_offer_discount_pct: number;
  shop_daily_offer_pack_id: number | null;
  club_league_enabled: boolean;
  club_league_points_game: number;
  club_league_points_pack: number;
  club_league_points_task: number;
  club_league_member_weekly_cap: number;
  club_league_rewards: number[];
  career_enabled: boolean;
  career_place_rewards: number[];
  career_difficulty_reward_pct: number[];
  career_difficulty_rating_offset: number[];
  career_match_reward_win: number;
  career_match_reward_draw: number;
  career_bot_growth_tenths: number;
  career_fatigue_per_match: number;
  career_fatigue_recovery: number;
  career_fatigue_penalty_pct: number;
  career_injury_chance_pct: number;
  career_yellow_chance_pct: number;
  career_red_chance_pct: number;
  career_yellows_for_ban: number;
  career_form_max: number;
  career_reminders_enabled: boolean;
  career_tactics_tuning: Record<string, unknown>;
  career_familiarity_axis_keep_pct: number;
  career_squad_size: number;
  career_ambition_bonus_pct: number[];
  career_ambition_rep_success: number[];
  career_ambition_rep_fail: number[];
  career_rep_title: number;
  career_rep_promotion: number;
  career_rep_relegation: number;
  career_rep_levels: number[];
  career_cup_enabled: boolean;
  career_cup_rewards: number[];
  career_rep_cup: number;
  career_offseason_auto: boolean;
  career_inactive_days: number;
  career_core_min: number;
  career_core_keep_pct: number;
  career_camp_physical_pct: number;
  career_camp_physical_rounds: number;
  career_camp_tactical_tenths: number;
  career_tenure_minutes_per_point: number;
  career_tenure_max: number;
  career_division_club_count: number;
  career_live_enabled: boolean;
  career_halftime_minutes: number;
  career_achievement_reward: number;
  career_digest_enabled: boolean;
  career_familiarity_step_tenths: number;
  career_familiarity_max_tenths: number;
  career_familiarity_keep_pct: number;
  career_max_plan_rules: number;
  career_max_substitutions: number;
  career_bot_counter_chance_pct: number[];
  career_division_count: number;
  career_division_promote: number;
  career_division_relegate: number;
  career_division_rating_offset: number[];
  career_division_reward_pct: number[];
  career_division_bot_level: string[];
  my_player_enabled: boolean;
  my_player_xp_per_reward: number;
  my_player_xp_daily_cap: number;
  my_player_xp_career_match: number;
  my_player_xp_level_base: number;
  my_player_xp_level_step: number;
  my_player_points_per_level: number;
  my_player_rating_cap: number;
  my_player_tier_thresholds: number[];
  my_player_training_xp_base: number;
  my_player_training_xp_per_hit: number;
  my_player_extra_trainings_max: number;
  my_player_extra_training_coins: number;
  my_player_extra_training_stars: number;
  player_career_enabled: boolean;
  player_career_min_club_cards: number;
  player_career_rating_margin: number;
  player_career_rep_per_club_rating: number;
  player_career_rep_per_goal: number;
  player_career_rep_per_assist: number;
  player_career_rep_per_win: number;
  player_career_rep_title: number;
  player_career_match_reward_win: number;
  player_career_match_reward_draw: number;
  player_career_goal_reward: number;
  player_career_match_xp: number;
  player_career_place_rewards: number[];
  my_player_cosmetic_prices: Record<string, number>;
  free_pack_pack_slug: string;
  chat_pack_interval_hours: number;
  referral_referred_reward: number;
  referral_referrer_reward: number;
  hangman_daily_limit: number;
  hangman_reward_correct: number;
  hangman_max_wrong: number;
  pairs_daily_limit: number;
  pairs_reward_perfect: number;
  pairs_reward_min: number;
  pairs_error_bracket_size: number;
  pairs_bracket_penalty: number;
  pairs_bonus_coins: number;
  tactico_challenge_expiry_hours: number;
  tactico_round_timeout_hours: number;
  tactico_phase_bonus_pct: number;
  tactico_reward_win: number;
  tactico_reward_draw: number;
  tactico_reward_loss: number;
  tactico_bot_optimal_pick_chance_easy: number;
  tactico_bot_optimal_pick_chance_medium: number;
  tactico_bot_optimal_pick_chance_hard: number;
  tactico_max_legendary_cards: number;
  tactico_max_epic_cards: number;
  tactico_max_diamond_cards: number;
  stratego_board_size: number;
  stratego_max_legendary_cards: number;
  stratego_max_diamond_cards: number;
  stratego_min_rare_cards: number;
  stratego_min_common_cards: number;
  stratego_my_player_xp: number;
  stratego_bot_easy_reward_pct: number;
  stratego_live_move_seconds: number;
  stratego_skill_bonus_per_level: number;
  stratego_puzzle_reward: number;
  stratego_tackler_max_rarity: "common" | "rare" | "epic" | "legendary" | "diamond";
  stratego_provocateur_max_rarity: "common" | "rare" | "epic" | "legendary" | "diamond";
  stratego_speedster_max_rarity: "common" | "rare" | "epic" | "legendary" | "diamond";
  stratego_tackler_count: number;
  stratego_speedster_count: number;
  stratego_wall_count: number;
  stratego_regular_count: number;
  stratego_move_limit: number;
  stratego_challenge_expiry_hours: number;
  stratego_move_timeout_hours: number;
  stratego_max_auto_moves: number;
  stratego_reward_win: number;
  stratego_reward_draw: number;
  stratego_reward_loss: number;
  stratego_daily_limit: number;
  magnate_start_money: number;
  magnate_pass_start_bonus: number;
  magnate_jail_fine: number;
  magnate_max_jail_turns: number;
  magnate_fine_amount: number;
  magnate_building_sell_pct: number;
  magnate_max_rounds: number;
  magnate_time_limit_minutes: number;
  magnate_turn_seconds: number;
  magnate_max_missed_turns: number;
  magnate_lobby_wait_seconds: number;
  magnate_room_wait_minutes: number;
  magnate_bot_buy_reserve: number;
  magnate_bot_build_reserve: number;
  magnate_bot_reward_pct: number;
  magnate_daily_limit: number;
  magnate_place_rewards: number[];
  magnate_stadium_rents: number[];
  /** null = built-in default (GET /admin/games/magnate-defaults). */
  magnate_board: MagnateBoardConfig | null;
  magnate_cards: Record<string, unknown> | null;
  match_max_diamond_cards: number;
  diamond_rating_cap: number;
  diamond_rating_cap_enabled: boolean;
  wheel_free_spins_per_day: number;
  wheel_spin_cost_coins: number;
  wheel_spin_cost_stars: number;
  wheel_duplicate_badge_coins: number;
  blackjack_enabled: boolean;
  blackjack_free_per_day: number;
  blackjack_stars_cost: number;
  blackjack_paid_daily_limit: number;
  blackjack_consolation_coins: number;
  bingo_reward_coins: number;
  bingo_reward_pack_id: number | null;
  card_skills_enabled: boolean;
  card_skill_level_1_bonus_pp: number;
  card_skill_level_2_bonus_pp: number;
  card_skill_level_3_bonus_pp: number;
  card_skill_event_bonus_cap_pp: number;
  card_skill_probability_floor_pct: number;
  card_skill_probability_ceiling_pct: number;
  card_skill_assign_token_cost: number;
  card_skill_assign_coin_cost: number;
  card_skill_upgrade_2_token_cost: number;
  card_skill_upgrade_2_coin_cost: number;
  card_skill_upgrade_3_token_cost: number;
  card_skill_upgrade_3_coin_cost: number;
  card_skill_replace_token_cost: number;
  card_skill_replace_coin_cost: number;
  /** Player-tournament place rewards in skill tokens; index 0 = 1st place. */
  ptour_place_skill_tokens: ({ skill_code: string; quantity: number } | null)[];
  chemistry_enabled: boolean;
  chemistry_link_strong: number;
  chemistry_link_medium: number;
  chemistry_threshold_1: number;
  chemistry_threshold_2: number;
  chemistry_threshold_3: number;
  chemistry_player_max: number;
  chemistry_player_floor: number;
  chemistry_rating_per_point: number;
  chemistry_off_position_penalty: number;
  chemistry_coach_country_points: number;
  chemistry_stadium_club_points: number;
}

export interface AdminSkillLedgerEntry {
  id: number;
  user_id: number;
  kind: string;
  skill_code: string;
  token_delta: number;
  token_balance_after: number;
  coins_spent: number;
  user_card_id: number | null;
  from_skill_code: string | null;
  from_level: number | null;
  to_skill_code: string | null;
  to_level: number | null;
  admin_id: number | null;
  related_object_type: string | null;
  related_object_id: number | null;
  reason: string | null;
  created_at: string;
}

export interface CardCollection {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  sort_order: number;
  image_path: string | null;
  reward_coins: number;
  reward_pack_id: number | null;
}

export type AdminWheelPrizePool = "regular" | "golden" | "jackpot";

export interface AdminWheelPrize {
  id: number;
  prize_type: "coins" | "pack" | "card_rarity" | "badge";
  pool: AdminWheelPrizePool;
  weight: number;
  is_active: boolean;
  sort_order: number;
  coins_amount: number | null;
  pack_id: number | null;
  card_rarity: "common" | "rare" | "epic" | "legendary" | null;
  badge_id: number | null;
}

export interface AdminWheelPoolSummary {
  pool: AdminWheelPrizePool;
  active_prizes: number;
  total_weight: number;
  expected_value_coins: number;
  prizes: { prize_id: number; probability: number; value_coins: number }[];
}

export interface AdminWheelPoolsSummary {
  pools: AdminWheelPoolSummary[];
  regular_spin_cost_coins: number;
  blackjack_p_jackpot: number;
  blackjack_p_golden: number;
  blackjack_p_loss: number;
  blackjack_consolation_coins: number;
  blackjack_expected_value_coins: number;
}

export interface DailyRewardOption {
  id: number;
  day: number;
  option_index: number;
  coins: number;
  free_pack_slug: string | null;
  grants_random_card: boolean;
}

export interface TaskDefinition {
  id: number;
  code: string;
  name: string;
  description: string;
  category: "regular" | "premium";
  condition_type: "metric_counter" | "match_min_rating" | "match_same_country" | "penalty_win_max_rating";
  metric: string | null;
  target_value: number;
  condition_params: Record<string, unknown> | null;
  reward_coins: number;
  reward_pack_id: number | null;
  reward_skill_code: string | null;
  reward_skill_tokens: number;
  channel_username: string | null;
  channel_chat_id: number | null;
  invite_link: string | null;
  is_active: boolean;
  sort_order: number;
  completed_count: number;
  claimed_count: number;
}

export interface SuspiciousMemorySession {
  session_id: number;
  user_id: number;
  username: string | null;
  score: number;
  reward_coins: number;
  created_at: string;
}

export interface SuspiciousMatch {
  match_id: number;
  user_id: number;
  username: string | null;
  user_score: number;
  opponent_score: number;
  reward_coins: number;
  created_at: string;
}

export interface AdminClub {
  id: number;
  name: string;
  club_type: "open" | "closed";
  logo_shape: "shield" | "circle" | "hexagon" | "star" | "diamond" | "banner" | "crest" | "chevron";
  logo_color: string;
  captain_id: number;
  member_count: number;
  budget: number;
  cups_count: number;
  stars_count: number;
  founded_at: string;
  is_disbanded: boolean;
}

export interface AdminClubDetail extends AdminClub {
  description: string;
  invite_code: string;
  last_tournament_applied_at: string | null;
}

export interface AdminClubMember {
  user_id: number;
  username: string | null;
  first_name: string | null;
  role: "captain" | "assistant" | "member";
  joined_at: string;
}

export interface AdminClubBudgetTransaction {
  id: number;
  amount: number;
  balance_before: number;
  balance_after: number;
  type: AdminClubBudgetTransactionType;
  description: string;
  created_at: string;
  user_id: number | null;
  user_name: string | null;
}

export type AdminClubBudgetTransactionType =
  | "daily_claim"
  | "pack_purchase"
  | "tournament_reward"
  | "tournament_match_reward"
  | "club_game_reward"
  | "club_missing_item_reward"
  | "club_penalty_reward"
  | "club_position_match_reward"
  | "coach_pack_purchase"
  | "admin_adjustment"
  | "league_reward";

export interface AdminClubTournament {
  tournament_id: number;
  status: "active" | "completed";
  rounds_simulated: number;
  points: number;
  goals_for: number;
  goals_against: number;
  is_withdrawn: boolean;
  final_rank: number | null;
  budget_awarded: number | null;
  stars_delta: number | null;
  cup_awarded: boolean | null;
}

export interface AdminTournamentSummary {
  id: number;
  status: "active" | "completed";
  rounds_simulated: number;
  club_count: number;
  created_at: string;
}

export interface AdminTournamentStats {
  active_count: number;
  completed_count: number;
  queued_club_count: number;
}

export type { Page, Pack, PackRarityProbability, Player, TradeOffer, TradeStatus };

export interface AdminLifestyleItem {
  id: number;
  name: string;
  description: string;
  category: string;
  emoji: string;
  image_path: string | null;
  coins_price: number;
  stars_price: number;
  prestige: number;
  max_supply: number | null;
  sold_count: number;
  is_active: boolean;
  sort_order: number;
}

export interface MagnateBoardCellConfig {
  type: string;
  name: string;
  group?: number;
  price?: number;
  rent?: number[];
  build_cost?: number;
}

export interface MagnateBoardConfig {
  groups: { name: string; color: string }[];
  cells: MagnateBoardCellConfig[];
}
