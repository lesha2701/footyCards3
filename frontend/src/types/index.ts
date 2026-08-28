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
  tactics_rating: number;
  penalty_rating: number;
  created_at: string;
  active_badge: Badge | null;
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
  attack_rating: number;
  defense_rating: number;
  rarity: Rarity;
  country: string;
  club: string;
  position: Position;
  image_path: string | null;
  quick_sell_price: number;
  is_active: boolean;
  is_pack_droppable: boolean;
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
  is_in_tactico_squad: boolean;
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
  extra_card_bonus: number;
  max_success_chance: number;
}

export interface CardUpgradeResult {
  success: boolean;
  from_rarity: Rarity;
  to_rarity: Rarity;
  card_count: number;
  success_chance: number;
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

export interface Badge {
  id: number;
  name: string;
  icon: string;
  image_path: string | null;
  is_active: boolean;
  sort_order: number;
}

export interface Pack {
  id: number;
  slug: string;
  name: string;
  description: string;
  price: number;
  stars_price: number | null;
  bonus_coins: number | null;
  badge_id: number | null;
  badge: Badge | null;
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

export interface StarsInvoiceCreate {
  invoice_link: string;
  payload_token: string;
  stars_amount: number;
}

export interface StarsCoinResult {
  coins_credited: number;
  new_balance: number;
}

export interface StarsInvoiceStatus {
  status: "pending" | "completed";
  result: PackOpenResult | null;
  coin_result: StarsCoinResult | null;
  gift_result: Gift | null;
  wheel_result: WheelSpinResult | null;
}

export interface WheelPrize {
  id: number;
  prize_type: "coins" | "pack" | "card_rarity" | "badge";
  weight: number;
  is_active: boolean;
  sort_order: number;
  coins_amount: number | null;
  pack_id: number | null;
  pack: Pack | null;
  card_rarity: "common" | "rare" | "epic" | "legendary" | null;
  badge_id: number | null;
  badge: Badge | null;
}

export interface WheelStatus {
  free_spins_remaining: number;
  free_spins_total: number;
  next_free_spin_reset_at: string;
  spin_cost_coins: number;
  spin_cost_stars: number;
  prizes: WheelPrize[];
}

export interface WheelSpinResult {
  prize: WheelPrize;
  new_balance: number;
  pack_result: PackOpenResult | null;
  card_result: OpenedCard | null;
  badge_result: Badge | null;
  duplicate_badge_coins: number | null;
  collection_rewards: CollectionRewardGrant[];
}

export interface CoinPackage {
  id: number;
  stars_price: number;
  coins_amount: number;
  is_active: boolean;
  sort_order: number;
}

export interface MemoryStart {
  session_id: number;
  round_number: number;
  sequence: string[];
  reveal_ms: number;
  answer_timeout_ms: number;
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

export interface ClubGameStart {
  session_id: number;
  round_number: number;
  icons: string[];
  sequence: string[];
  reveal_ms: number;
  answer_timeout_ms: number;
}

export interface ClubGameSubmitResult {
  correct: boolean;
  session_id: number;
  score: number;
  status: string;
  next_round?: ClubGameStart;
}

export interface ClubGameClaimResult {
  reward_coins: number;
  new_club_budget: number;
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

export interface MaintenanceStatus {
  active: boolean;
  until: string | null;
}

export interface UpdateBroadcastStatus {
  broadcast_at: string | null;
}

export interface FeatureFlags {
  matchmaking_enabled: boolean;
  wheel_enabled: boolean;
  leagues_enabled: boolean;
}

export interface GameLimits {
  hourly_limit: number;
  memory: number;
  arena: number;
  saboteur: number;
  penalty: number;
  free_kick: number;
  hangman: number;
  tactico: number;
  pairs: number;
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

export type RankingMetric =
  | "arena_rating"
  | "matches_won"
  | "cards_count"
  | "unique_players"
  | "referral_count"
  | "tactics_rating"
  | "penalty_rating"
  | "league_rating";

export interface RankingEntry {
  rank: number;
  user_id: number;
  display_name: string;
  avatar_url: string | null;
  value: number;
  active_badge: Badge | null;
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
  active_badge: Badge | null;
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

export interface TacticoSquad {
  is_complete: boolean;
  cards: UserCard[];
  max_legendary: number;
  max_epic: number;
}

export interface TacticoStats {
  tactics_rating: number;
  tactics_rank: number | null;
}

export interface PenaltyStats {
  penalty_rating: number;
  penalty_rank: number | null;
}

export type TacticoPhase = "attack" | "defense";
export type TacticoOpponentType = "bot" | "friend" | "online";
export type TacticoMatchStatus = "pending_accept" | "in_progress" | "finished" | "declined" | "cancelled" | "expired";

export interface TacticoSearchStatus {
  status: "not_searching" | "searching" | "matched" | "timeout";
  match_id: number | null;
  created_at: string | null;
}

export interface TacticoCard {
  user_card_id: number | null;
  player_id: number;
  display_name: string;
  position: Position;
  image_path: string | null;
  rarity: Rarity;
  rating: number;
  attack_rating: number;
  defense_rating: number;
}

export interface TacticoRound {
  index: number;
  phase: TacticoPhase;
  user_card: TacticoCard | null;
  opponent_card: TacticoCard | null;
  winner: "user" | "opponent" | "draw" | null;
}

export interface TacticoMatch {
  id: number;
  opponent_type: TacticoOpponentType;
  opponent_name: string;
  opponent_user_id: number | null;
  difficulty: "easy" | "medium" | "hard" | null;
  status: TacticoMatchStatus;
  viewer_side: "user" | "opponent";
  user_score: number;
  opponent_score: number;
  rounds: TacticoRound[];
  current_phase: TacticoPhase | null;
  pickable_cards: TacticoCard[] | null;
  waiting_for_opponent: boolean;
  round_deadline: string | null;
  result: "win" | "draw" | "loss" | null;
  reward_coins: number;
  rating_delta: number;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
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
  league_rank: number;
  matches_won: number;
  matches_drawn: number;
  matches_lost: number;
  memory_best_score: number;
  unique_cards: number;
  total_cards: number;
  rarest_card: Player | null;
  packs_opened: number;
  referral_count: number;
  active_badge: Badge | null;
  tactics_rating: number;
  tactics_matches_won: number;
  tactics_matches_drawn: number;
  tactics_matches_lost: number;
  penalty_rating: number;
  penalty_matches_won: number;
  penalty_matches_drawn: number;
  penalty_matches_lost: number;
}

export interface ProfilePrivate extends ProfilePublic {
  telegram_id: number;
  balance: number;
  experience: number;
  is_admin: boolean;
  telegram_bot_username: string;
  accept_trades: boolean;
  referral_reward_pending: boolean;
  referral_referrer_reward: number;
  referral_referred_reward: number;
  daily_login_streak: number;
}

export interface ProfileSettingsUpdate {
  accept_trades?: boolean;
  active_badge_id?: number | null;
}

export interface OwnedBadge {
  badge: Badge;
  equipped: boolean;
}

export interface TrophyDefinition {
  id: number;
  code: string;
  name: string;
  description: string;
  icon: string;
  image_path: string | null;
  is_active: boolean;
  sort_order: number;
}

export interface LeagueTier {
  id: number;
  name: string;
  min_rating: number;
  color: string;
  image_path: string | null;
  reward_coins: number;
  reward_pack_id: number | null;
  sort_order: number;
}

export interface LeagueTierPublic {
  id: number;
  name: string;
  min_rating: number;
  color: string;
  image_path: string | null;
  reward_coins: number;
  reward_pack_name: string | null;
  sort_order: number;
}

export interface LeagueRewardClaim {
  id: number;
  tier_name: string;
  color: string;
  image_path: string | null;
  reward_coins: number;
  reward_pack_name: string | null;
  granted_at: string;
}

export interface LeagueStatus {
  total_rating: number;
  arena_rating: number;
  tactics_rating: number;
  penalty_rating: number;
  current_league: LeagueTierPublic | null;
  next_league: LeagueTierPublic | null;
  points_to_next: number | null;
  current_league_percent: number | null;
  unseen_rewards: LeagueRewardClaim[];
}

export interface UserTrophy {
  id: number;
  trophy: TrophyDefinition;
  message: string | null;
  granted_at: string;
  granted_by_admin_id: number | null;
}

export interface GiftSet {
  id: number;
  name: string;
  description: string;
  image_path: string | null;
  kind: "bundle" | "collectible";
  pack_id: number | null;
  coins_amount: number;
  stars_price: number;
  coins_price: number;
  max_supply: number | null;
  next_serial_number: number;
  collection_id: number | null;
  is_active: boolean;
  sort_order: number;
}

export interface Gift {
  id: number;
  gift_set: GiftSet;
  sender: UserPublic | null;
  message: string | null;
  is_admin_gift: boolean;
  is_pinned: boolean;
  serial_number: number | null;
  claimed_at: string | null;
  created_at: string;
}

export interface GiftClaimResult {
  gift: Gift;
  pack_result: PackOpenResult | null;
  coins_credited: number;
  new_balance: number;
}

export interface GiftPurchaseResult {
  gift: Gift;
  new_balance: number;
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

export type PenaltyDirection =
  | "top_left" | "top_center" | "top_right"
  | "bottom_left" | "bottom_center" | "bottom_right";

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
  rating_delta: number | null;
}

export interface PenaltyClaimResult {
  reward_coins: number;
  new_balance: number;
  result: string;
}

export interface PenaltyForfeitResult {
  session_id: number;
  player_score: number;
  bot_score: number;
  result: string;
  rating_delta: number;
}

export type PenaltyMatchStatus = "pending_accept" | "in_progress" | "finished" | "declined" | "cancelled" | "expired";
export type PenaltyOpponentType = "friend" | "online";

export interface PenaltyRound {
  kicker: "user" | "opponent";
  shot_zone: PenaltyDirection;
  dive_zone: PenaltyDirection;
  outcome: "goal" | "saved" | "miss";
}

export interface PenaltyMatch {
  id: number;
  opponent_name: string;
  opponent_type: PenaltyOpponentType;
  opponent_user_id: number | null;
  status: PenaltyMatchStatus;
  viewer_side: "user" | "opponent";
  user_score: number;
  opponent_score: number;
  rounds: PenaltyRound[];
  kicker: "user" | "opponent" | null;
  is_viewer_turn: boolean;
  kick_deadline: string | null;
  match_deadline: string | null;
  result: MatchResult | null;
  rating_delta: number;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}

export interface PenaltySearchStatus {
  status: "not_searching" | "searching" | "matched" | "timeout";
  match_id: number | null;
  created_at: string | null;
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

export interface PairsStartResult {
  session_id: number;
  board_size: number;
  total_pairs: number;
}

export interface PairsCard {
  position: number;
  is_bonus: boolean;
  player: Player | null;
}

export interface PairsFlipResult {
  session_id: number;
  revealed: PairsCard[];
  matched: boolean | null;
  matched_pairs: number;
  wrong_attempts: number;
  total_pairs: number;
  status: "in_progress" | "won" | "lost" | "rewarded" | "expired";
}

export interface PairsClaimResult {
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

export type ClubType = "open" | "closed";
export type ClubRole = "captain" | "assistant" | "member";
export type ClubLogoShape = "shield" | "circle" | "hexagon" | "star" | "diamond" | "banner" | "crest" | "chevron";

export interface ClubMember {
  user_id: number;
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  role: ClubRole;
  joined_at: string;
}

export interface ClubSummary {
  id: number;
  name: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  member_count: number;
  cups_count: number;
  stars_count: number;
}

export interface Club {
  id: number;
  name: string;
  description: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  captain_id: number;
  founded_at: string;
  member_count: number;
  members: ClubMember[];
  invite_code: string | null;
  my_role: ClubRole | null;
  budget: number;
  cups_count: number;
  stars_count: number;
  daily_reward_seconds_remaining: number | null;
}

export interface ClubJoinRequest {
  id: number;
  user_id: number;
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  created_at: string;
  status: "pending" | "accepted" | "rejected";
}

export interface ClubCard {
  id: number;
  serial_number: number;
  player: Player;
  acquired_at: string;
  is_in_lineup: boolean;
}

export interface ClubLineupSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  card: ClubCard | null;
}

export interface ClubLineup {
  is_complete: boolean;
  team_strength: number | null;
  slots: ClubLineupSlot[];
}

export interface ClubPackRarityProbability {
  rarity: string;
  probability: number;
}

export interface ClubPack {
  id: number;
  slug: string;
  name: string;
  description: string;
  price: number;
  card_count: number;
  guaranteed_min_rarity: string | null;
  image_path: string | null;
  is_active: boolean;
  sort_order: number;
  rarity_probabilities: ClubPackRarityProbability[];
}

export interface OpenedClubCard {
  card: ClubCard;
  is_new: boolean;
}

export interface ClubPackOpenResult {
  opening_id: number;
  pack: ClubPack;
  cards: OpenedClubCard[];
  new_budget: number;
}

export type ClubRankingMetric = "cups" | "stars";

export interface ClubRankingEntry {
  rank: number;
  club_id: number;
  name: string;
  logo_shape: ClubLogoShape;
  logo_color: string;
  value: number;
}

export interface ClubRankingResult {
  metric: ClubRankingMetric;
  top: ClubRankingEntry[];
  me: ClubRankingEntry | null;
}

export type TournamentCurrentStatus = "not_queued" | "queued" | "active" | "completed";

export interface TournamentApplyResult {
  queued: boolean;
  tournament_id: number | null;
  queue_position: number | null;
}

export interface TournamentCurrent {
  status: TournamentCurrentStatus;
  queue_position: number | null;
  tournament_id: number | null;
  can_apply: boolean;
  cooldown_seconds_remaining: number | null;
}

export interface TournamentStanding {
  club_id: number;
  club_name: string;
  points: number;
  goals_for: number;
  goals_against: number;
  final_rank: number | null;
  budget_awarded: number | null;
  stars_delta: number | null;
  cup_awarded: boolean | null;
}

export interface TournamentMatchSummary {
  id: number;
  round_number: number;
  club_a_id: number;
  club_b_id: number;
  score_a: number;
  score_b: number;
}

export interface TournamentDetail {
  id: number;
  status: string;
  rounds_simulated: number;
  standings: TournamentStanding[];
  matches: TournamentMatchSummary[];
  next_round_seconds_remaining: number | null;
}

export interface TournamentMatchDetail {
  id: number;
  round_number: number;
  club_a_id: number;
  club_b_id: number;
  score_a: number;
  score_b: number;
  event_log: MatchEvent[];
}
