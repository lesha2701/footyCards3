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
  match_daily_energy: number;
  match_reward_win: number;
  match_reward_draw: number;
  match_reward_loss: number;
  difficulty_easy_multiplier: number;
  difficulty_medium_multiplier: number;
  difficulty_hard_multiplier: number;
  suspicious_score_margin: number;
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
}

export interface CardCollection {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  sort_order: number;
}

export interface TaskDefinition {
  id: number;
  code: string;
  name: string;
  description: string;
  category: "regular" | "premium";
  condition_type: "metric_counter" | "match_min_rating";
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
