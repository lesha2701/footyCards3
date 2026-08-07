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
  arena_rating: number;
  created_at: string;
  last_seen_at: string | null;
}

export interface PackPreview {
  simulations: number;
  cards_per_open: number;
  rarity_distribution: { rarity: Rarity; count: number; percentage: number }[];
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
  saboteur_cell_reward: number;
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
  free_pack_interval_hours: number;
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
  pairs_penalty_per_wrong: number;
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

export type { Page, Pack, PackRarityProbability, Player, TradeOffer, TradeStatus };
