export type Rarity = "common" | "rare" | "epic" | "legendary";
export type Position = "GK" | "LB" | "CB" | "RB" | "CDM" | "CM" | "CAM" | "LM" | "RM" | "LW" | "RW" | "ST";
export type TradeStatus = "pending" | "accepted" | "rejected" | "cancelled" | "expired";
export type MatchDifficulty = "easy" | "medium" | "hard";
export type MatchResult = "win" | "draw" | "loss";
export type MatchStatus = "in_progress" | "finished";
export type ShotType = "in_box" | "long_range" | "empty_net";
export type LineupTactic = "attacking" | "balanced" | "defensive";
export type MatchActionKind = "shoot" | "pass" | "tackle" | "block" | "keeper" | "strike";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface UserMe {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  balance: number;
  is_admin: boolean;
  level: number;
  experience: number;
  arena_rating: number;
  matches_won: number;
  matches_drawn: number;
  matches_lost: number;
  memory_best_score: number;
  created_at: string;
}

export interface AuthResponse {
  user: UserMe;
  admin_token: string | null;
}

export interface Player {
  id: number;
  first_name: string;
  last_name: string;
  display_name: string;
  rating: number;
  rarity: Rarity;
  country: string;
  club: string;
  position: Position;
  image_path: string | null;
  quick_sell_price: number;
  is_active: boolean;
  collection_id: number | null;
  collection_name: string | null;
}

export interface UserCard {
  id: number;
  serial_number: number;
  player: Player;
  acquired_at: string;
  source: string;
  is_locked_by_admin: boolean;
  is_locked_in_trade: boolean;
  is_in_lineup: boolean;
  hidden_from_trade: boolean;
  duplicate_count?: number;
}

export interface CardUpgradeRule {
  id: number;
  from_rarity: Rarity;
  to_rarity: Rarity;
  success_chance: number;
  coin_cost: number;
  is_active: boolean;
}

export interface CardUpgradeResult {
  success: boolean;
  from_rarity: Rarity;
  to_rarity: Rarity;
  coin_cost: number;
  new_card: UserCard | null;
  new_balance: number;
}

export interface CollectionStats {
  unique_players: number;
  total_cards: number;
  by_rarity: Record<string, number>;
}

export interface PackRarityProbability {
  rarity: Rarity;
  probability: number;
}

export interface Pack {
  id: number;
  slug: string;
  name: string;
  description: string;
  price: number;
  image_path: string | null;
  card_count: number;
  guaranteed_min_rarity: Rarity | null;
  is_active: boolean;
  purchase_limit_per_user: number | null;
  available_from: string | null;
  available_until: string | null;
  rarity_probabilities: PackRarityProbability[];
  user_purchase_count: number;
  is_available_now: boolean;
}

export interface OpenedCard {
  card: UserCard;
  is_new: boolean;
  duplicate_count: number;
}

export interface CollectionRewardGrant {
  collection_id: number;
  collection_name: string;
  reward_coins: number;
  granted_pack: PackOpenResult | null;
}

export interface PackOpenResult {
  opening_id: number;
  pack: Pack;
  cards: OpenedCard[];
  new_balance: number;
  referral_bonus_coins: number | null;
  collection_rewards: CollectionRewardGrant[];
}

export interface MemoryStart {
  session_id: number;
  round_number: number;
  sequence: string[];
  reveal_ms: number;
}

export interface MemorySubmitResult {
  correct: boolean;
  session_id: number;
  score: number;
  status: string;
  next_round?: MemoryStart;
}

export interface MemoryClaimResult {
  reward_coins: number;
  new_balance: number;
  new_best_score: boolean;
  best_score: number;
}

export interface MemoryLeaderboardEntry {
  user_id: number;
  display_name: string;
  avatar_url: string | null;
  best_score: number;
}

export interface LineupSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  card: UserCard | null;
}

export interface Lineup {
  id: number | null;
  formation: string;
  tactic: LineupTactic;
  is_complete: boolean;
  team_strength: number | null;
  slots: LineupSlot[];
}

export interface MatchEvent {
  minute: number;
  event_type: string;
  team: string;
  description: string;
  payload?: Record<string, unknown> | null;
}

export interface MatchActor {
  user_card_id: number;
  player_id: number;
  name: string;
  rating: number;
  position: string;
}

export interface MatchPendingMoment {
  seq: number;
  team: "user" | "opponent";
  kind: "attack" | "defense" | "breakaway";
  shot_type: ShotType;
  description: string;
  actions: MatchActionKind[];
  actors: Record<string, MatchActor>;
}

export interface Match {
  id: number;
  opponent_name: string;
  difficulty: MatchDifficulty;
  user_team_strength: number;
  opponent_team_strength: number;
  user_score: number;
  opponent_score: number;
  status: MatchStatus;
  result: MatchResult | null;
  reward_coins: number;
  rating_delta: number;
  created_at: string;
  events: MatchEvent[];
  pending_moment: MatchPendingMoment | null;
}

export interface ArenaStats {
  matches_won: number;
  matches_drawn: number;
  matches_lost: number;
  arena_rating: number;
  arena_rank: number | null;
}

export interface ArenaLeaderboardEntry {
  user_id: number;
  display_name: string;
  avatar_url: string | null;
  arena_rating: number;
  matches_won: number;
  matches_drawn: number;
  matches_lost: number;
  goal_difference: number;
  points: number;
}

export type RankingMetric = "arena_rating" | "matches_won" | "cards_count" | "unique_players" | "referral_count";

export interface RankingEntry {
  rank: number;
  user_id: number;
  display_name: string;
  avatar_url: string | null;
  value: number;
}

export interface RankingResult {
  metric: RankingMetric;
  top: RankingEntry[];
  me: RankingEntry | null;
}

export interface UserPublic {
  id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  level: number;
  arena_rating: number;
  created_at: string;
}

export interface TradeOffer {
  id: number;
  sender: UserPublic;
  receiver: UserPublic;
  status: TradeStatus;
  sender_coins: number;
  receiver_coins: number;
  message: string | null;
  offered_cards: UserCard[];
  requested_cards: UserCard[];
  expires_at: string;
  resolved_at: string | null;
  created_at: string;
}

export interface DailyRewardDay {
  day: number;
  coins: number;
  free_pack_name: string | null;
  grants_random_card: boolean;
  is_claimed: boolean;
  is_today: boolean;
}

export interface DailyRewardCalendar {
  current_streak: number;
  already_claimed_today: boolean;
  days: DailyRewardDay[];
}

export interface DailyRewardClaimResult {
  streak_day: number;
  coins_awarded: number;
  new_balance: number;
  granted_card: UserCard | null;
  granted_pack_name: string | null;
}

export interface ProfilePublic {
  id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  avatar_url: string | null;
  created_at: string;
  level: number;
  arena_rating: number;
  arena_rank: number;
  matches_won: number;
  matches_drawn: number;
  matches_lost: number;
  memory_best_score: number;
  unique_cards: number;
  total_cards: number;
  rarest_card: Player | null;
  packs_opened: number;
  referral_count: number;
}

export interface ProfilePrivate extends ProfilePublic {
  telegram_id: number;
  balance: number;
  experience: number;
  is_admin: boolean;
  telegram_bot_username: string;
  accept_trades: boolean;
  referral_reward_pending: boolean;
}

export interface ProfileSettingsUpdate {
  accept_trades?: boolean;
}

export interface CoinTransaction {
  id: number;
  amount: number;
  balance_before: number;
  balance_after: number;
  type: string;
  description: string;
  related_object_type: string | null;
  related_object_id: number | null;
  created_at: string;
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  body: string;
  related_object_type: string | null;
  related_object_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface Task {
  user_task_id: number;
  code: string;
  name: string;
  description: string;
  category: "regular" | "premium";
  reward_coins: number;
  reward_pack_name: string | null;
  channel_username: string | null;
  invite_link: string | null;
  progress: number;
  target_value: number;
  is_completed: boolean;
  is_claimed: boolean;
}

export interface TaskList {
  regular: Task[];
  premium: Task[];
}

export interface TaskClaimResult {
  reward_coins: number;
  new_balance: number;
  granted_pack: PackOpenResult | null;
  refilled_task: Task | null;
}

export interface SaboteurStartResult {
  session_id: number;
  line_size: number;
  steward_count: number;
  level: number;
}

export interface SaboteurRevealResult {
  is_steward: boolean;
  session_id: number;
  score: number;
  level: number;
  status: string;
  reward_coins: number | null;
}

export interface SaboteurClaimResult {
  reward_coins: number;
  new_balance: number;
}

export type PenaltyDirection = "left" | "center" | "right";

export interface PenaltyStartResult {
  session_id: number;
  player_rating: number;
  first_kicker: "player" | "bot";
}

export interface PenaltyKickResult {
  session_id: number;
  kicker: "player" | "bot";
  outcome: "goal" | "saved" | "miss";
  player_direction: PenaltyDirection | null;
  bot_direction: PenaltyDirection;
  player_score: number;
  bot_score: number;
  next_kicker: "player" | "bot" | null;
  is_finished: boolean;
  result: "win" | "draw" | "loss" | null;
}

export interface PenaltyClaimResult {
  reward_coins: number;
  new_balance: number;
  result: string;
}

export interface FreeKickNextKick {
  kick_index: number;
  period_ms: number;
  start_ts: string;
  half_width: number;
}

export interface FreeKickStartResult {
  session_id: number;
  kick: FreeKickNextKick;
}

export interface FreeKickKickResult {
  tier: "perfect" | "good" | "ok" | "miss";
  coins_this_kick: number;
  total_coins: number;
  is_finished: boolean;
  next_kick: FreeKickNextKick | null;
}

export interface FreeKickClaimResult {
  reward_coins: number;
  new_balance: number;
}

export interface HangmanStartResult {
  session_id: number;
  category: "player" | "term";
  masked_word: string[];
  max_wrong: number;
}

export interface HangmanGuessResult {
  session_id: number;
  masked_word: string[];
  guessed_letters: string[];
  wrong_letters: string[];
  max_wrong: number;
  status: "in_progress" | "won" | "lost" | "rewarded" | "expired";
  is_correct: boolean;
  word: string | null;
}

export interface HangmanClaimResult {
  reward_coins: number;
  new_balance: number;
}

export interface FreePackStatus {
  available: boolean;
  available_at: string | null;
}

export interface CardCollectionPublic {
  id: number;
  name: string;
}

export interface AlbumCollectionSummary {
  id: number; // -1 for the synthetic "Other players" bucket
  name: string;
  description: string;
  image_path: string | null;
  owned_count: number;
  total_count: number;
  is_complete: boolean;
  reward_coins: number;
  reward_pack_name: string | null;
  reward_claimed: boolean;
}

export interface AlbumOverview {
  collections: AlbumCollectionSummary[];
  overall_owned: number;
  overall_total: number;
}

export interface AlbumPlayer {
  player: Player;
  owned: boolean;
  duplicate_count: number;
  card: UserCard | null;
}

export interface AlbumCollectionDetail {
  id: number;
  name: string;
  description: string;
  image_path: string | null;
  reward_coins: number;
  reward_pack_name: string | null;
  owned_count: number;
  total_count: number;
  is_complete: boolean;
  reward_claimed: boolean;
  players: AlbumPlayer[];
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
