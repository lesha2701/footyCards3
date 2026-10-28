import type { ManagerStyle } from "@/api/manager";
import type { Muse } from "@/api/muses";
export type Rarity = "common" | "rare" | "epic" | "legendary" | "diamond";
export type Position = "GK" | "LB" | "CB" | "RB" | "LWB" | "RWB" | "CDM" | "CM" | "CAM" | "LM" | "RM" | "LW" | "RW" | "ST";
export type TradeStatus = "pending" | "accepted" | "rejected" | "cancelled" | "expired";
export type MatchDifficulty = "easy" | "medium" | "hard";
export type MatchResult = "win" | "draw" | "loss";
export type MatchStatus = "in_progress" | "finished";
export type ShotType = "in_box" | "long_range" | "empty_net";
export type LineupTactic = "attacking" | "possession" | "defensive" | "counter";
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
  /** «Академия»: set = a path card with this talent. */
  path_talent_code?: string | null;
  /** «Один футболист» key; null = by the display name. */
  person_key?: string | null;
}

export type CoachBoostType =
  | "attack_central" | "attack_wing" | "midfield_control"
  | "defence_central" | "defence_wing" | "goalkeeping"
  | "passing_accuracy" | "ball_control" | "defensive_discipline"
  | "counter_mastery" | "squad_stability";

export interface CoachBoost {
  id: number;
  boost_type: CoachBoostType;
  magnitude: number;
}

export interface Coach {
  id: number;
  display_name: string;
  rarity: Rarity;
  image_path: string | null;
  /** «Тренер-земляк»: players of this country get extra chemistry. */
  country?: string | null;
  quick_sell_price: number;
  is_active: boolean;
  is_pack_droppable: boolean;
  boosts: CoachBoost[];
}

export interface Stadium {
  id: number;
  display_name: string;
  rarity: Rarity;
  image_path: string | null;
  /** «Домашний стадион»: players of this club get extra chemistry at home. */
  club?: string | null;
  quick_sell_price: number;
  is_active: boolean;
  is_pack_droppable: boolean;
  boost_pct: number;
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
  /** The owner's own «замок»: can't be sold or burned as material. */
  is_user_locked?: boolean;
  /** «Путь дебютанта» gift: no trade, sale or burning until this moment. */
  bound_until?: string | null;
  /** Stands in a player-tournament squad (no flag of its own on the card). */
  in_personal_squad?: boolean;
  duplicate_count?: number;
  diamond_rating_bonus: number;
  /** This copy's own skill (null = none). See CardSkillBadge / CardSkillPanel. */
  skill_code?: string | null;
  skill_level?: number | null;
  /** Collection list only: every skilled copy of this player (the list
   * collapses duplicates into one representative). */
  skilled_copies?: SkilledCopy[];
  /** «Звёзды карточки»: earned stars, duplicates banked toward the next one
   * and the rating the stars add (already included in player.rating). */
  stars?: number;
  star_progress?: number;
  star_rating_bonus?: number;
  /** «Академия»: levels gained, stage reached (0 = Новичок …) and the
   * rating the levels add (already included in player.rating). */
  path_level?: number;
  path_stage?: number;
  path_rating_bonus?: number;
  /** «Экипировка» it wears (already included in player.rating). */
  equipment_rating_bonus?: number;
  /** Its worn things: +chemistry and the boosts (shot/save/…, a national-team set). */
  equipment_chemistry?: number;
  equipment_boosts?: Record<string, unknown> | null;
  /** «Академия» prestige tier, its «Икона» number and the reforged talent. */
  prestige?: number;
  prestige_icon_number?: number | null;
  talent_override?: string | null;
}

export interface CardStarState {
  card_id: number;
  player_id: number;
  rarity: Rarity;
  enabled: boolean;
  block_reason: string | null;
  stars: number;
  max_stars: number;
  progress: number;
  thresholds: number[];
  coin_costs: number[];
  next_threshold: number | null;
  next_coin_cost: number | null;
  claimable: boolean;
  dupes_to_max: number;
  rating_base: number;
  rating_now: number;
  rating_bonus: number;
  rating_after_next_star: number | null;
  free_duplicates: { id: number; serial_number: number; skill_code: string | null; skill_level: number | null }[];
}

export interface CardStarOperation {
  kind: "feed" | "claim";
  cards_consumed: number;
  stars_gained: number;
  coins_spent: number;
  new_balance: number;
  replayed: boolean;
  state: CardStarState;
}

export interface SkilledCopy {
  id: number;
  serial_number: number;
  skill_code: string;
  skill_level: number;
}

export interface DiamondUpgradeTier {
  id: number;
  min_rating: number;
  max_rating: number;
  // null means that rarity cannot be used to level up a card in this band.
  common_cost: number | null;
  rare_cost: number | null;
  epic_cost: number | null;
  legendary_cost: number | null;
  is_active: boolean;
}

export interface FeedCardsResult {
  diamond_card: UserCard;
  material_rarity: Rarity;
  cards_consumed: number;
  cards_returned: number;
  rating_gained: number;
}

export type DiamondMaterialBandKind = "admin_tier" | "any_diamond" | "same_player_diamond";

export interface DiamondMaterialCardsOut {
  kind: DiamondMaterialBandKind;
  cost: number | null;
  ceiling: number;
  cards: UserCard[];
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
  /** At most this many a day per player (e.g. «Легенда дня»). */
  daily_limit_per_user?: number | null;
  available_from: string | null;
  available_until: string | null;
  rarity_probabilities: PackRarityProbability[];
  coach_drop_chance: number;
  stadium_drop_chance: number;
  skill_token_drop_chance?: number;
  /** Per-slot chance of a «Муза» instead of a footballer (the «Музы» pack: 0.1). */
  muse_drop_chance?: number;
  /** "path" = the «Академия» pack (diamond slots drop only path cards). */
  player_pool?: string;
  /** Why the pack cannot be bought right now (e.g. no «Академия» players yet). */
  unavailable_reason?: string | null;
  user_purchase_count: number;
  /** Bought today (counted for a pack with daily_limit_per_user). */
  user_today_count?: number;
  is_available_now: boolean;
  /** Average quick-sell value of the cards inside (shop listing only). */
  expected_value?: number | null;
  /** Paid packs left until the guaranteed legendary (null = off / no legendary here). */
  pity_left?: number | null;
  /** Discount on opening 10+ at once, % (0 = none). */
  bulk10_discount_pct?: number;
}

export interface OpenedCard {
  card: UserCard;
  is_new: boolean;
  duplicate_count: number;
}

export interface UserCoachCard {
  id: number;
  serial_number: number;
  coach: EquippedCoach;
  acquired_at: string;
}

export interface OpenedCoachCard {
  card: UserCoachCard;
  is_new: boolean;
  duplicate_count: number;
}

export interface UserStadiumCard {
  id: number;
  serial_number: number;
  stadium: EquippedStadium;
  acquired_at: string;
}

export interface OpenedStadiumCard {
  card: UserStadiumCard;
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
  coach_cards: OpenedCoachCard[];
  stadium_cards: OpenedStadiumCard[];
  /** Pack slots that rolled card-skill tokens instead of a card. */
  skill_tokens?: { skill_code: string; quantity: number }[];
  /** Pack slots that dropped a «Муза» instead of a card. */
  muses?: OpenedMuse[];
  new_balance: number;
  referral_bonus_coins: number | null;
  collection_rewards: CollectionRewardGrant[];
}

/** A pack slot that dropped a «Муза» (see api/muses.ts Muse). */
export interface OpenedMuse {
  muse: Muse;
  is_new: boolean;
  copies: number;
}

export interface PackBulkOpenResult {
  pack: Pack;
  quantity: number;
  opening_ids: number[];
  cards: OpenedCard[];
  coach_cards: OpenedCoachCard[];
  stadium_cards: OpenedStadiumCard[];
  /** Pack slots that rolled card-skill tokens instead of a card. */
  skill_tokens?: { skill_code: string; quantity: number }[];
  /** Pack slots that dropped a «Муза» instead of a card. */
  muses?: OpenedMuse[];
  new_balance: number;
  total_price_paid: number;
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
  blackjack_result?: { kind: "entry"; paid_entries?: number } | null;
}

export type WheelPrizePool = "regular" | "golden" | "jackpot";

export interface WheelPrize {
  id: number;
  prize_type: "coins" | "pack" | "card_rarity" | "badge";
  pool: WheelPrizePool;
  weight: number;
  is_active: boolean;
  sort_order: number;
  coins_amount: number | null;
  pack_id: number | null;
  pack: Pack | null;
  card_rarity: Rarity | null;
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

export interface BlackjackCard {
  hidden: boolean;
  rank: string | null;
  suit: "gk" | "df" | "mf" | "fw" | null;
}

export type BlackjackOutcome = "hat_trick" | "win" | "push" | "loss";

export interface BlackjackMatch {
  id: number;
  status: "in_progress" | "finished";
  entry_source: "free" | "paid" | "replay";
  player_cards: BlackjackCard[];
  player_total: number;
  player_soft: boolean;
  dealer_cards: BlackjackCard[];
  dealer_total: number;
  outcome: BlackjackOutcome | null;
  outcome_reason: string | null;
  reward_pool: WheelPrizePool | null;
  prize: WheelPrize | null;
  consolation_coins: number;
  created_at: string;
  finished_at: string | null;
}

export interface BlackjackAction {
  match: BlackjackMatch;
  new_balance: number;
  spin_result: WheelSpinResult | null;
}

export interface BlackjackStatus {
  enabled: boolean;
  free_per_day: number;
  free_remaining: number;
  paid_entries: number;
  replay_entries: number;
  paid_bought_today: number;
  paid_daily_limit: number;
  stars_cost: number;
  consolation_coins: number;
  next_reset_at: string;
  active_match: BlackjackMatch | null;
  golden_prizes: WheelPrize[];
  jackpot_prizes: WheelPrize[];
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
  /** «+N%» set by the admin (already inside coins_amount); 0 = computed from the price. */
  bonus_pct?: number;
  is_active: boolean;
  sort_order: number;
  /** Extra coins on this player's first coin purchase (0 once they have bought). */
  first_purchase_bonus_coins?: number;
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
  daily_cap_reached: boolean;
}

export interface ClubPenaltyStart {
  session_id: number;
  player_rating: number;
  first_kicker: "player" | "bot";
}

export interface ClubPenaltyKick {
  session_id: number;
  kicker: "player" | "bot";
  outcome: "goal" | "saved" | "miss";
  player_direction: PenaltyDirection | null;
  bot_direction: PenaltyDirection;
  player_score: number;
  bot_score: number;
  next_kicker: "player" | "bot" | null;
  is_finished: boolean;
  result: "win" | "loss" | null;
}

export interface ClubPenaltyClaim {
  reward_coins: number;
  new_club_budget: number;
  result: string;
  daily_cap_reached: boolean;
}

export interface ClubPenaltyForfeit {
  session_id: number;
  player_score: number;
  bot_score: number;
  result: string;
}

export interface ClubPositionMatchCard {
  id: number;
  display_name: string;
  rating: number;
  rarity: Rarity;
  image_path: string | null;
}

export interface ClubPositionMatchStart {
  session_id: number;
  cards: ClubPositionMatchCard[];
  positions: string[];
  max_mistakes: number;
}

export interface ClubPositionMatchAttempt {
  session_id: number;
  correct: boolean;
  matched_player_ids: number[];
  mistakes: number;
  max_mistakes: number;
  status: "in_progress" | "won" | "lost" | "rewarded" | "expired";
}

export interface ClubPositionMatchClaim {
  reward_coins: number;
  new_club_budget: number;
  daily_cap_reached: boolean;
}

export interface LineupSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  card: UserCard | null;
}

export interface Lineup {
  id: number | null;
  template_index: number;
  name: string;
  is_active: boolean;
  formation: string;
  tactic: LineupTactic;
  is_complete: boolean;
  team_strength: number | null;
  max_diamond: number;
  /** «Академия» cards: own limit next to the diamond one. */
  max_path?: number;
  coach: EquippedCoach | null;
  stadium: EquippedStadium | null;
  slots: LineupSlot[];
  chemistry?: ChemistryOut;
}

export type ChemistryLinkLevel = "strong" | "medium" | "none";

export interface ChemistryRules {
  link_strong: number;
  link_medium: number;
  thresholds: number[];
  player_max: number;
  player_floor: number;
  rating_per_point: number;
  off_position_penalty: number;
  coach_country_points?: number;
  stadium_club_points?: number;
}

export interface ChemistryLink {
  a: string;
  b: string;
  level: ChemistryLinkLevel;
  points: number;
}

export interface PlayerChemistry {
  slot_code: string;
  points: number;
  link_sum: number;
  on_position: boolean;
  rating_bonus: number;
  /** Extra points from «тренер-земляк» / «домашний стадион» (before the cap). */
  coach_bonus?: number;
  stadium_bonus?: number;
}

/** Neighbour-link chemistry of a lineup (backend services/chemistry_service.py).
 * enabled=false: the mechanic is off, only strength_bonus (old flat bonus) is set. */
export interface ChemistryOut {
  enabled: boolean;
  strength_bonus: number | null;
  /** Rules come from a tournament that is already running (frozen at its start), not from live settings. */
  frozen?: boolean;
  /** Whether the mechanic is switched on in the live settings right now. */
  live_enabled?: boolean;
  formation: string | null;
  coach_country?: string | null;
  stadium_club?: string | null;
  team: number;
  team_max: number;
  links: ChemistryLink[];
  players: PlayerChemistry[];
  adjacency: [string, string][];
  rules: ChemistryRules | null;
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
  /** «Академия»: static talents applied at kickoff / experience earned. */
  talent_notes?: MatchTalentNote[] | null;
  path_progress?: PathMatchProgress[] | null;
  /** Card Arena divisions: styles/chances at kickoff, points, the report. */
  arena?: MatchArenaInfo | null;
  ladder?: ArenaLadderResult | null;
  report?: ArenaMatchReport | null;
}

export type ArenaMatchup = "win" | "loss" | "neutral";

export interface ArenaChances {
  win: number;
  draw: number;
  loss: number;
}

export interface MatchArenaInfo {
  user_style: LineupTactic;
  opponent_style: LineupTactic;
  user_formation?: string;
  opponent_formation?: string;
  matchup: ArenaMatchup;
  matchup_bonus_pct: number;
  chances: ArenaChances | null;
  opponent_points: number | null;
}

export interface ArenaLadderResult {
  points_before: number;
  points_after: number;
  delta: number;
  division_before: number;
  division_after: number;
  promoted: boolean;
  relegated: boolean;
  shield_used: boolean;
  shield_left: number;
  rewards: { division: number; coins: number }[];
}

export interface ArenaLineCompare {
  key: "GK" | "DEF" | "MID" | "FWD";
  label: string;
  user: number;
  opponent: number;
}

export interface ArenaMatchReport {
  verdict: string;
  reasons: string[];
  chances: ArenaChances;
  user_strength: number;
  opponent_strength: number;
  user_style: LineupTactic;
  opponent_style: LineupTactic;
  matchup: ArenaMatchup;
  matchup_bonus_pct: number;
  lines: ArenaLineCompare[];
  user_chances: number;
  opponent_chances: number;
  user_keeper_saves: number;
  opponent_keeper_saves: number;
}

export interface ArenaDivision {
  division: number;
  total_divisions: number;
  points: number;
  min_points: number;
  next_min_points: number | null;
  shield_matches: number;
  coin_pct: number;
  next_reward_coins: number | null;
}

export interface ArenaPreview {
  opponent_name: string;
  opponent_avatar_url: string | null;
  opponent_is_bot: boolean;
  opponent_points: number;
  opponent_division: number;
  opponent_strength: number;
  opponent_style: LineupTactic;
  opponent_formation: string;
  user_strength: number;
  user_style: LineupTactic;
  user_formation: string;
  matchup: ArenaMatchup;
  matchup_bonus_pct: number;
  matchup_text: string;
  lines: ArenaLineCompare[];
  chances: ArenaChances;
  points_at_stake: Record<MatchResult, number>;
  division: ArenaDivision;
}

export interface ArenaStats {
  matches_won: number;
  matches_drawn: number;
  matches_lost: number;
  arena_rating: number;
  /** Place by arena points (null before the first division match). */
  arena_rank: number | null;
  division?: ArenaDivision | null;
}

export interface MaintenanceStatus {
  active: boolean;
  until: string | null;
}

export interface UpdateBroadcastStatus {
  broadcast_at: string | null;
}

export interface Announcement {
  text: string | null;
  updated_at: string | null;
}

export interface FeatureFlags {
  matchmaking_enabled: boolean;
  wheel_enabled: boolean;
  /** Admin switch: off = no new trade offers and no accepting. */
  trades_enabled?: boolean;
  leagues_enabled: boolean;
  /** Largest stake per side in open chat challenges; 0 = stakes off. */
  stake_max_coins?: number;
}

export interface GameLimits {
  hourly_limit: number;
  /** The free kick's own cap of series per hour. */
  free_kick_hourly_limit?: number;
  memory: number;
  arena: number;
  saboteur: number;
  penalty: number;
  free_kick: number;
  hangman: number;
  tactico: number;
  pairs: number;
  stratego: number;
  magnate: number;
  mordoboi: number;
  kontra?: number;
  /** Exhausted games only: when the hourly cap frees up again. */
  resets_at?: Partial<Record<string, string>>;
}

export interface ArenaLeaderboardEntry {
  user_id: number;
  display_name: string;
  avatar_url: string | null;
  arena_rating: number;
  arena_points?: number;
  division?: number;
  matches_won: number;
  matches_drawn: number;
  matches_lost: number;
  goal_difference: number;
  points: number;
}

export type RankingMetric =
  | "academy_level"
  | "base_level"
  | "academy_prestige"
  | "arena_rating"
  | "matches_won"
  | "cards_count"
  | "unique_players"
  | "referral_count"
  | "tactics_rating"
  | "penalty_rating"
  | "stratego_rating"
  | "stratego_puzzles"
  | "mordoboi_rating"
  | "kontra_rating"
  | "games_week"
  | "stars_week"
  | "referrals_week"
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
  template_index: number;
  name: string;
  is_active: boolean;
  is_complete: boolean;
  cards: UserCard[];
  max_legendary: number;
  max_epic: number;
  max_diamond: number;
  max_path?: number;
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
export type TacticoOpponentType = "bot" | "friend" | "online" | "chat";
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
  stake_coins: number;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}

export interface TacticoOpenChallengePreview {
  id: number;
  creator_name: string;
  stake_coins: number;
  status: TacticoMatchStatus;
  is_own_challenge: boolean;
}

// --- Monetization: reward slots, login calendar, club pass, season pass,
// starter offer, cosmetics (backend schemas/monetization.py) ---

export type CosmeticKind =
  | "profile_frame"
  | "profile_background"
  | "card_skin"
  | "brutality"
  | "ring_gloves"
  | "ring_shorts"
  | "ring_entrance"
  | "helmet";

export interface Cosmetic {
  id: number;
  kind: CosmeticKind;
  name: string;
  description: string | null;
  style_key: string;
  coins_price: number;
  stars_price: number;
  is_exclusive: boolean;
  is_active: boolean;
  sort_order: number;
  /** «Статус» of «Мой игрок» while owned. */
  status: number;
  /** Uploaded picture (shown instead of the style's built-in look). */
  image_path?: string | null;
  /** «Бруталити»: coins added to the win when applied. */
  win_bonus_coins?: number;
}

export interface CosmeticCatalogItem extends Cosmetic {
  owned: boolean;
  equipped: boolean;
}

export interface EquippedCosmetics {
  frame: string | null;
  background: string | null;
  card_skin: string | null;
}

export interface CosmeticCatalog {
  items: CosmeticCatalogItem[];
  equipped: EquippedCosmetics;
  balance: number;
}

/** What one reward slot contains — shown before claiming or paying. */
export interface RewardBundle {
  coins: number;
  pack_id: number | null;
  pack_name: string | null;
  card_rarity: Rarity | null;
  badge: Badge | null;
  cosmetic: Cosmetic | null;
}

export interface GrantedRewards {
  coins: number;
  pack_name: string | null;
  cards: UserCard[];
  badge: Badge | null;
  cosmetic: Cosmetic | null;
  new_balance: number;
}

export type CalendarDayStatus = "claimed" | "today" | "missed" | "future";

export interface CalendarDay {
  day: number;
  date: string;
  reward: RewardBundle;
  status: CalendarDayStatus;
  claim_method: string | null;
  is_big: boolean;
}

export interface LoginCalendar {
  month: string;
  today: string;
  days: CalendarDay[];
  claimed_count: number;
  days_in_month: number;
  already_claimed_today: boolean;
  month_bonus: RewardBundle;
  month_bonus_claimed: boolean;
  catchup_coins: number;
  catchup_stars: number;
  catchups_left: number;
  /** «Клубный абонемент»: free catch-ups left this month. */
  free_catchups_left: number;
}

export interface CalendarClaimResult {
  day: number;
  granted: GrantedRewards;
  month_bonus: GrantedRewards | null;
  new_balance: number;
}

export interface ClubPassPerks {
  /** «Статус» of «Мой игрок» while the pass is active. */
  status: number;
  daily_coins: number;
  daily_pack: RewardBundle | null;
  /** Granted with every paid month. */
  monthly_bonus: RewardBundle | null;
  extra_rewarded_attempts: number;
  season_xp_bonus_pct: number;
  free_catchups: number;
  frame: Cosmetic | null;
  badge: Badge | null;
  ad_free: boolean;
}

export interface ClubPass {
  enabled: boolean;
  stars_price: number;
  perks: ClubPassPerks;
  is_active: boolean;
  expires_at: string | null;
  auto_renew: boolean;
  daily_claimed_today: boolean;
}

export interface SeasonLevel {
  level: number;
  xp_required: number;
  free: RewardBundle;
  premium: RewardBundle;
  reached: boolean;
  free_claimed: boolean;
  premium_claimed: boolean;
}

export interface SeasonPass {
  enabled: boolean;
  season_id: number | null;
  name: string | null;
  starts_at: string | null;
  ends_at: string | null;
  premium_stars: number;
  xp: number;
  level: number;
  next_level_xp: number | null;
  is_premium: boolean;
  levels: SeasonLevel[];
  claimable: number;
  locked_premium: number;
  xp_per_game: number;
  xp_per_daily_claim: number;
  premium_status: number;
}

export type ArtifactTarget = "club" | "my_player";

export interface ArtifactInfo {
  id: number;
  name: string;
  description: string | null;
  image_path: string | null;
  icon: string;
  rarity: Rarity;
  target: ArtifactTarget;
  target_label: string;
  effect: string;
  effect_value: number;
  effect_label: string;
  /** Stronger with a card of this stadium / coach / player. */
  link_type: "stadium" | "coach" | "player" | null;
  link_kind: string;
  link_name: string | null;
  link_label: string;
  link_owned: boolean;
  /** «+3 к рейтингу карточек «Марадона»» — "" when none. */
  card_player_name: string | null;
  card_label: string;
  /** The value that applies to this player (link bonus included). */
  active_label: string;
  coins_price: number;
  stars_price: number;
  /** «Статус» of «Мой игрок» while owned (once per artifact). */
  status: number;
  max_supply: number | null;
  left: number | null;
}

export interface ArtifactShopItem extends ArtifactInfo {
  owned_count: number;
}

export interface ArtifactCopy {
  copy_id: number;
  serial_number: number;
  equipped: boolean;
  source: string;
  artifact: ArtifactInfo;
}

export interface ArtifactEffect {
  effect: string;
  value: number;
  label: string;
}

export interface ArtifactCatalog {
  enabled: boolean;
  slots: number;
  active_count: number;
  shop: ArtifactShopItem[];
  shelf: ArtifactCopy[];
  effects: Record<ArtifactTarget, ArtifactEffect[]>;
  balance: number;
}

export interface StarterOffer {
  available: boolean;
  stars_price: number;
  contents: RewardBundle;
  expires_at: string | null;
  seen: boolean;
  purchased: boolean;
}

export interface ProfilePublic {
  id: number;
  cosmetics?: EquippedCosmetics;
  club_pass_active?: boolean;
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
  /** A friend counts after this many days of play. */
  referral_active_days?: number;
  referral_milestones?: { count: number; reward: RewardBundle; reached: boolean }[];
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
  pack_count?: number;
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
  reward_skill_code?: string | null;
  reward_skill_tokens?: number;
  channel_username: string | null;
  invite_link: string | null;
  progress: number;
  target_value: number;
  is_completed: boolean;
  is_claimed: boolean;
  period?: "daily" | "weekly";
  /** Activity points the claim adds to its day / week track. */
  points?: number;
  /** Where «Играть →» leads; null = nowhere. */
  route?: string | null;
  /** A pinned must-do premium subscription (the game's channel / chat). */
  is_required?: boolean;
}

export interface TaskChest {
  index: number;
  points: number;
  coins: number;
  card_rarity: Rarity | null;
  pack_id: number | null;
  is_claimed: boolean;
  is_available: boolean;
}

export interface TaskTrack {
  period_key: string;
  points: number;
  max_points: number;
  chests: TaskChest[];
  resets_at: string;
}

export interface TaskList {
  /** Today's set. */
  regular: Task[];
  weekly?: Task[];
  premium: Task[];
  daily_track?: TaskTrack | null;
  weekly_track?: TaskTrack | null;
  rerolls_left?: number;
  /** «Свой в клубе»: earned by every required subscription. */
  required_badge?: Badge | null;
}

export interface TaskChestClaimResult {
  rewards: GrantedRewards;
  new_balance: number;
}

export interface TaskRerollResult {
  task: Task;
  rerolls_left: number;
}

export interface TaskClaimResult {
  reward_coins: number;
  new_balance: number;
  granted_pack: PackOpenResult | null;
  granted_skill_tokens?: { skill_code: string; quantity: number } | null;
  refilled_task: Task | null;
  points_added?: number;
  granted_badge?: Badge | null;
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
export type PenaltyOpponentType = "friend" | "online" | "chat";

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
  stake_coins: number;
  reward_coins: number;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}

export interface PenaltyOpenChallengePreview {
  id: number;
  creator_name: string;
  stake_coins: number;
  status: PenaltyMatchStatus;
  is_own_challenge: boolean;
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

/** One position of a 3D free kick series: the scene is
 * `createSetup(seed, rating)`, exactly what the server replays. */
export interface FreeKick3DKick {
  kick_index: number;
  seed: number;
}

export interface FreeKick3DStartResult {
  session_id: number;
  rating: number;
  total_kicks: number;
  kick: FreeKick3DKick;
}

export interface FreeKick3DShotResult {
  outcome: "goal" | "save" | "miss" | "wall";
  bonuses: ("corner" | "curl")[];
  coins_this_kick: number;
  total_coins: number;
  is_finished: boolean;
  next_kick: FreeKick3DKick | null;
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

export interface FutDraftConfig {
  entry_cost: number;
  reward_by_wins: number[];
}

export interface FutDraftCandidate {
  id: number;
  display_name: string;
  rating: number;
  rarity: Rarity;
  position: string;
  club: string;
  country: string;
  image_path: string | null;
}

export interface FutDraftSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  player: FutDraftCandidate | null;
}

export interface FutDraftStart {
  session_id: number;
  formation_options: string[];
  entry_cost: number;
  new_balance: number;
}

export interface FutDraftState {
  session_id: number;
  formation: string;
  phase: "drafting" | "ready";
  slots: FutDraftSlot[];
  pending_slot: string | null;
  candidates: FutDraftCandidate[] | null;
  team_strength: number;
  last_pick_strength_delta: number | null;
  chemistry_hints: string[];
}

export type FutDraftGameType = "card_arena" | "tactico" | "penalty" | "coin_flip";
export type FutDraftCoinFlipChoice = "heads" | "tails";

// Mirrors the backend's FutDraftRoundOut: one round of one of the three
// flavors, either mid-play (round_in_progress=true, driven one turn at a
// time via submitFutDraftCardArenaAction/submitFutDraftTacticoPhase/
// submitFutDraftPenaltyKick) or fully resolved (round_in_progress=false,
// result/wins/is_finished populated). Card Arena events/pending_moment
// reuse MatchEvent/MatchPendingMoment field-for-field — it's the exact same
// match_service engine, just against a temporary draft squad.
export interface FutDraftRound {
  session_id: number;
  game_type: FutDraftGameType;
  round_in_progress: boolean;

  events: MatchEvent[];
  pending_moment: MatchPendingMoment | null;
  opponent_name: string | null;

  phase: number | null;
  total_phases: number | null;
  tactic_choices: string[] | null;
  last_phase_result: string | null;

  kick_number: number | null;
  picked_player: FutDraftCandidate | null;
  zone_choices: string[] | null;
  last_kick_result: string | null;

  // A drawn round is decided by a coin flip instead of ending the series
  // outright — call heads or tails, guess right and it's a win.
  coin_flip_choices: FutDraftCoinFlipChoice[] | null;
  coin_flip_result: FutDraftCoinFlipChoice | null;

  user_score: number;
  bot_score: number;

  round_number: number | null;
  result: "win" | "draw" | "loss" | null;
  wins: number;
  is_finished: boolean;
  status: string;
}

export interface FutDraftClaim {
  reward_coins: number;
  new_balance: number;
  wins: number;
  team_strength: number;
  is_new_best: boolean;
  best_squad_strength: number;
}

export interface FutDraftLeaderboardEntry {
  user_id: number;
  display_name: string;
  avatar_url: string | null;
  best_squad_strength: number;
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
export type ClubRole = "captain" | "vice_captain" | "assistant" | "treasurer" | "member";
export type ClubLogoShape = "shield" | "circle" | "hexagon" | "star" | "diamond" | "banner" | "crest" | "chevron";

/** Paid layers on top of logo_shape/logo_color (club_emblem_service). */
export interface ClubEmblem {
  color2: string | null;
  pattern: string | null;
  symbol: string | null;
  letters: string | null;
  outline: string | null;
  outline_thin: boolean;
  effect: string | null;
}

export type ClubEmblemKind = "color2" | "pattern" | "letters" | "symbol" | "outline" | "effect";
export type ClubSponsorTier = "bronze" | "silver" | "gold";

export interface ClubEmblemItem {
  id: number;
  kind: ClubEmblemKind;
  style_key: string;
  name: string;
  coins_price: number;
  stars_price: number;
  is_active: boolean;
  sort_order: number;
}

export interface ClubEmblemState {
  enabled: boolean;
  club_id: number;
  logo_shape: ClubLogoShape;
  logo_color: string;
  emblem: ClubEmblem;
  items: (ClubEmblemItem & { unlocked: boolean })[];
  budget: number;
  star_balance: number;
  can_edit: boolean;
  can_spend_budget: boolean;
}

export interface ClubPatron {
  user_id: number;
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  stars: number;
  coins: number;
  tier: ClubSponsorTier;
  is_member: boolean;
}

export interface ClubTreasury {
  enabled: boolean;
  club_id: number;
  budget: number;
  star_balance: number;
  coins_per_star: number;
  star_options: number[];
  silver_stars: number;
  gold_stars: number;
  my_stars: number;
  my_tier: ClubSponsorTier | null;
  patrons: ClubPatron[];
  recent: { user_id: number; username: string | null; first_name: string | null; stars: number; coins: number; created_at: string }[];
}

export interface ClubMember {
  user_id: number;
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  role: ClubRole;
  joined_at: string;
  personal_reward_enabled: boolean;
  sponsor_tier?: ClubSponsorTier | null;
}

export interface ClubLeagueRow {
  rank: number;
  club_id: number;
  name: string;
  logo_shape: ClubLogoShape;
  logo_color: string;
  emblem?: ClubEmblem | null;
  points: number;
  reward: number;
}

export interface ClubLeagueMember {
  user_id: number;
  name: string;
  games: number;
  packs: number;
  tasks: number;
  points: number;
}

export interface ClubSeasonRow {
  rank: number;
  club_id: number;
  name: string;
  logo_shape: ClubLogoShape;
  logo_color: string;
  emblem?: ClubEmblem | null;
  points: number;
  zone: "up" | "down" | null;
}

export interface ClubLeague {
  enabled: boolean;
  division?: number;
  division_names?: string[];
  division_reward_pct?: number;
  season?: {
    weeks: number;
    week_of_season: number;
    ends_at: string;
    promote_count: number;
    relegate_count: number;
    standings: ClubSeasonRow[];
    my_row: ClubSeasonRow | null;
  } | null;
  week_start: string;
  ends_at: string;
  points_game: number;
  points_pack: number;
  points_task: number;
  member_weekly_cap: number;
  rewards: number[];
  clubs_count: number;
  table: ClubLeagueRow[];
  my_row: ClubLeagueRow | null;
  members: ClubLeagueMember[];
  last_week: { week_start: string; podium: ClubLeagueRow[]; my_row: ClubLeagueRow | null } | null;
}

export interface ClubMemberActivity {
  user_id: number;
  username: string | null;
  first_name: string | null;
  role: ClubRole;
  games_played: number;
  daily_rewards_claimed: number;
}

export interface ClubStats {
  matches_played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_scored: number;
  goals_conceded: number;
  win_rate_pct: number;
  draw_rate_pct: number;
  loss_rate_pct: number;
  goals_scored_per_match: number;
  goals_conceded_per_match: number;
}

export interface ClubSummary {
  id: number;
  name: string;
  club_type: ClubType;
  logo_shape: ClubLogoShape;
  logo_color: string;
  emblem?: ClubEmblem | null;
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
  emblem?: ClubEmblem | null;
  captain_id: number;
  founded_at: string;
  member_count: number;
  members: ClubMember[];
  invite_code: string | null;
  my_role: ClubRole | null;
  budget: number;
  budget_treasurer_only?: boolean;
  star_balance?: number;
  can_spend_budget?: boolean;
  wall_unread?: number | null;
  rewards_unclaimed?: number | null;
  cups_count: number;
  stars_count: number;
  daily_reward_seconds_remaining: number | null;
  personal_match_earnings: number | null;
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

export interface ClubCardAvailability {
  reason: "red_card" | "injury";
  rounds_remaining: number;
}

export interface ClubCard {
  id: number;
  serial_number: number;
  player: Player;
  acquired_at: string;
  is_in_lineup: boolean;
  availability: ClubCardAvailability | null;
}

export interface ClubPost {
  id: number;
  user_id: number;
  username: string | null;
  first_name: string | null;
  avatar_url: string | null;
  role: ClubRole | null;
  text: string;
  is_announcement: boolean;
  is_pinned: boolean;
  created_at: string;
  can_delete: boolean;
}

export interface ClubWall {
  posts: ClubPost[];
  can_announce: boolean;
  can_pin: boolean;
  announce_cooldown_seconds: number;
}

export interface ClubReward {
  id: number;
  source: string;
  title: string;
  reward: RewardBundle;
  created_at: string;
  expires_at: string;
}

export interface ClubQuests {
  enabled: boolean;
  week_start: string;
  ends_at: string;
  quests: { id: number; title: string; metric: "games" | "packs" | "tasks"; target: number; progress: number; completed: boolean; reward_budget: number; reward: RewardBundle }[];
  members: { user_id: number; name: string; games: number; packs: number; tasks: number }[];
}

export interface ClubTrophies {
  club_id: number;
  name: string;
  logo_shape: ClubLogoShape;
  logo_color: string;
  emblem?: ClubEmblem | null;
  division: number;
  division_name: string;
  cups_count: number;
  stars_count: number;
  founded_at: string;
  seasons: { season_end_week: string; division: number; division_name: string; rank: number; points: number; moved: number }[];
  league_gold: number;
  league_silver: number;
  league_bronze: number;
  recent_podiums: { week_start: string; division: number; division_name: string; rank: number; points: number }[];
  tournaments_played: number;
  tournaments_won: number;
  best_tournament_rank: number | null;
  recent_tournaments: { tournament_id: number; final_rank: number; cup: boolean; played_at: string }[];
  quests_completed: number;
  wars_played: number;
  wars_won: number;
}

export interface ClubWarSide {
  club_id: number;
  name: string;
  logo_shape: ClubLogoShape;
  logo_color: string;
  emblem?: ClubEmblem | null;
  war_rating: number;
  score: number;
  members: { user_id: number; name: string; games: number; packs: number; tasks: number; points: number; ring_points?: number }[];
}

export interface ClubWar {
  enabled: boolean;
  state: "none" | "upcoming" | "active" | "finished";
  starts_at: string;
  ends_at: string;
  duration_hours: number;
  min_members: number;
  member_count: number;
  war_rating: number;
  win_budget: number;
  draw_budget: number;
  loss_budget: number;
  win_member_coins: number;
  war_id: number | null;
  me: ClubWarSide | null;
  opponent: ClubWarSide | null;
  result: "win" | "loss" | "draw" | null;
  history: { war_id: number; opponent_name: string; my_score: number; opponent_score: number; result: "win" | "loss" | "draw"; ended_at: string }[];
}

export interface ClubShop {
  budget: number;
  can_buy: boolean;
  member_count: number;
  items: { id: number; name: string; description: string; price: number; weekly_limit: number; bought_this_week: number; reward: RewardBundle }[];
  rewards: ClubReward[];
}

export interface ClubSurplus {
  enabled: boolean;
  can_manage: boolean;
  budget: number;
  sell_pct: number;
  exchange_count: number;
  cards: { card: ClubCard; protected: boolean; sell_value: number }[];
  exchange_pack: ClubPack | null;
}

export interface ClubLineupSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  card: ClubCard | null;
}

export interface ClubLineup {
  template_index: number;
  name: string;
  is_active: boolean;
  is_complete: boolean;
  team_strength: number | null;
  formation: string;
  mentality: string;
  playstyle: string;
  tactical_fit: number;
  tactical_fit_hint: string;
  coach: EquippedCoach | null;
  stadium: EquippedStadium | null;
  slots: ClubLineupSlot[];
  training_uses_remaining: number;
  training_boost_active: boolean;
  in_active_tournament: boolean;
  attack: number;
  midfield: number;
  defence: number;
  goalkeeping: number;
  chemistry?: ChemistryOut;
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
  coach_drop_chance: number;
  stadium_drop_chance: number;
  rarity_probabilities: ClubPackRarityProbability[];
}

export interface OpenedClubPackItem {
  kind: "player" | "coach" | "stadium";
  card: ClubCard | null;
  coach_card: ClubCoachCard | null;
  stadium_card: ClubStadiumCard | null;
  is_new: boolean;
}

export interface ClubPackOpenResult {
  opening_id: number;
  pack: ClubPack;
  cards: OpenedClubPackItem[];
  new_budget: number;
}

export type ClubRankingMetric = "cups" | "stars";

export interface ClubRankingEntry {
  rank: number;
  club_id: number;
  name: string;
  logo_shape: ClubLogoShape;
  logo_color: string;
  emblem?: ClubEmblem | null;
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

export interface NextOpponent {
  round_number: number;
  opponent_club_id: number;
  opponent_club_name: string;
  attack: number;
  midfield: number;
  defence: number;
  goalkeeping: number;
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

export interface PersonalSquadSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  user_card_id: number | null;
  serial_number: number | null;
  player: Player | null;
  skill_code?: string | null;
  skill_level?: number | null;
  /** The copy's rating with its own bonuses; the slot fit (100 / 90 / 75 %);
   * the chemistry bonus; what it plays at: (rating + chemistry) × fit. */
  rating?: number | null;
  fit_pct?: number;
  chemistry_bonus?: number;
  match_rating?: number | null;
  stars?: number;
  path_stage?: number;
  prestige?: number;
}

export interface PersonalSquad {
  template_index: number;
  name: string;
  is_active: boolean;
  is_complete: boolean;
  formation: string;
  mentality: string;
  playstyle: string;
  /** Card Arena style the tournament plays with. */
  style: ManagerStyle;
  slots: PersonalSquadSlot[];
  coach: EquippedCoach | null;
  stadium: EquippedStadium | null;
  chemistry?: ChemistryOut;
}

export type PlayerTournamentStatus = "not_queued" | "queued" | "active" | "completed";

export interface PlayerTournamentApplyResult {
  queued: boolean;
  tournament_id: number | null;
  queue_position: number | null;
  queue_size: number;
}

export interface PlayerTournamentCurrent {
  status: PlayerTournamentStatus;
  queue_position: number | null;
  queue_size: number;
  tournament_id: number | null;
  can_apply: boolean;
  tournaments_played: number;
  stars_count: number;
  cups_count: number;
}

export interface PlayerTournamentStanding {
  user_id: number;
  display_name: string;
  points: number;
  goals_for: number;
  goals_against: number;
  final_rank: number | null;
  coins_awarded: number | null;
  stars_delta: number | null;
  cup_awarded: boolean | null;
}

export interface PlayerTournamentMatchSummary {
  id: number;
  round_number: number;
  user_a_id: number;
  user_b_id: number;
  score_a: number;
  score_b: number;
}

export interface PlayerTournamentDetail {
  id: number;
  status: string;
  rounds_simulated: number;
  standings: PlayerTournamentStanding[];
  matches: PlayerTournamentMatchSummary[];
  next_round_seconds_remaining: number | null;
}

export interface PlayerTournamentMatchDetail {
  id: number;
  round_number: number;
  user_a_id: number;
  user_b_id: number;
  user_a_name: string;
  user_b_name: string;
  score_a: number;
  score_b: number;
  event_log: MatchEvent[];
}

export type PlayerTournamentRankingMetric = "cups" | "stars";

export interface PlayerTournamentRankingEntry {
  rank: number;
  user_id: number;
  display_name: string;
  value: number;
}

export interface PlayerTournamentRankingResult {
  metric: PlayerTournamentRankingMetric;
  top: PlayerTournamentRankingEntry[];
  me: PlayerTournamentRankingEntry | null;
}

export interface PlayerTournamentStats {
  matches_played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_scored: number;
  goals_conceded: number;
  win_rate_pct: number;
  draw_rate_pct: number;
  loss_rate_pct: number;
  goals_scored_per_match: number;
  goals_conceded_per_match: number;
}

export type BingoGoalType =
  | "packs_opened"
  | "rare_drops"
  | "epic_drops"
  | "legendary_drops"
  | "tactico_matches_played"
  | "penalty_matches_played"
  | "arena_matches_played"
  | "trades_completed";

export interface BingoGoal {
  goal_type: BingoGoalType;
  target_value: number;
  current_value: number;
  is_completed: boolean;
}

export interface BingoCurrent {
  is_enabled: boolean;
  week_number: number | null;
  starts_at: string | null;
  ends_at: string | null;
  goals: BingoGoal[];
  all_goals_completed: boolean;
  reward_coins: number;
  reward_pack_id: number | null;
  reward_pack_name: string | null;
  reward_pack_image_path: string | null;
  has_claimed: boolean;
}

export interface BingoClaimResult {
  coins_granted: number;
  granted_pack: PackOpenResult | null;
  new_balance: number;
}

export interface BingoGoalDefinition {
  id: number;
  goal_type: BingoGoalType;
  target_value: number;
  is_active: boolean;
}

export interface BingoState {
  is_enabled: boolean;
  started_at: string | null;
}

export interface BingoStatsPreviewItem {
  goal_type: BingoGoalType;
  trailing_7d_count: number;
}

export interface EquippedCoach {
  id: number;
  display_name: string;
  rarity: Rarity;
  image_path: string | null;
  country?: string | null;
  boosts: CoachBoost[];
}

export interface ClubCoachCard {
  id: number;
  serial_number: number;
  coach: EquippedCoach;
  acquired_at: string;
}

export interface EquippedStadium {
  id: number;
  display_name: string;
  rarity: Rarity;
  image_path: string | null;
  club?: string | null;
  boost_pct: number;
}

export interface ClubStadiumCard {
  id: number;
  serial_number: number;
  stadium: EquippedStadium;
  acquired_at: string;
}


// --- Card skills (backend: services/card_skill_service.py) ---

export type SkillOperation = "assign" | "upgrade" | "replace";

export interface SkillLevelEffect {
  level: number;
  level_label: string;
  bonus_pp: number;
}

export interface SkillCatalogItem {
  code: string;
  name: string;
  icon: string;
  effect: string;
  applies_in: string[];
  not_affected: string;
  positions: string[];
  max_positions: string[];
  levels: SkillLevelEffect[];
  /** Plain-language tail for "+N% …", e.g. "к точности удара". */
  bonus_phrase: string;
  /** Match engines the skill acts in: "arena" (Card Arena), "tournament". */
  engines: string[];
  engine_supported: boolean;
  is_enabled: boolean;
  is_available: boolean;
  unavailable_reason: string | null;
  remaining_work: string[];
  sort_order: number;
  pack_drop_weight: number;
  pack_drop_quantity: number;
}

export interface SkillCost {
  token_cost: number;
  coin_cost: number;
}

export interface SkillCatalog {
  rules: {
    enabled: boolean;
    max_level: number;
    event_bonus_cap_pp: number;
    probability_floor_pct: number;
    probability_ceiling_pct: number;
    costs: { assign: SkillCost; upgrade_to_2: SkillCost; upgrade_to_3: SkillCost; replace: SkillCost };
  };
  skills: SkillCatalogItem[];
}

export interface SkillTokenBalance {
  skill_code: string;
  quantity: number;
}

export interface CardSkillInfo {
  code: string;
  level: number;
  level_label: string;
  bonus_pp: number;
  is_effective: boolean;
}

export interface SkillAction {
  operation: SkillOperation;
  skill_code: string;
  target_level: number;
  token_cost: number;
  coin_cost: number;
  tokens_owned: number;
  allowed: boolean;
  reason: string | null;
  /** False when the skill can never go on this card's position. */
  position_compatible: boolean;
}

export interface CardCopy {
  id: number;
  serial_number: number;
  skill_code: string | null;
  skill_level: number | null;
  is_locked_in_trade: boolean;
  is_in_lineup: boolean;
  is_in_tactico_squad: boolean;
  is_locked_by_admin: boolean;
}

export interface CardSkillState {
  card_id: number;
  serial_number: number;
  player_id: number;
  player_name: string;
  position: string;
  skill: CardSkillInfo | null;
  next_level_bonus_pp: number | null;
  blocked_reason: string | null;
  actions: SkillAction[];
  copies: CardCopy[];
}

export interface SkillOperationResult {
  operation: SkillOperation;
  card_id: number;
  skill_code: string;
  skill_level: number;
  previous_skill_code: string | null;
  previous_level: number | null;
  token_cost: number;
  coin_cost: number;
  tokens_left: number;
  new_balance: number;
  replayed: boolean;
}

/** One entry of a match event payload's `skills` list. */
export interface MatchSkillNote {
  code: string;
  name: string;
  level: number;
  level_label: string;
  bonus_pp: number;
  player: string | null;
  decisive: boolean;
}

// --- Футбольное Стратего ---

export type StrategoRole = "cup" | "wall" | "star" | "tackler" | "provocateur" | "speedster" | "regular";

export interface StrategoCard {
  user_card_id: number | null;
  player_id: number;
  display_name: string;
  position: string;
  image_path: string | null;
  rarity: Rarity;
  rating: number;
  is_my_player?: boolean;
  /** «Академия»: own squad limit. */
  is_path?: boolean;
  skill_name?: string | null;
  skill_level?: number | null;
  skill_kind?: "atk" | "def" | null;
  skill_bonus?: number;
}

export type StrategoNoteTag = "cup" | "wall" | "star" | "strong" | "weak" | "speedster";
export type StrategoDifficulty = "easy" | "normal" | "hard";

export interface StrategoPuzzleBrief {
  code: string;
  title: string;
  description: string;
  moves: number;
}

export interface StrategoPuzzle extends StrategoPuzzleBrief {
  reward: number;
  solved_today: boolean;
  solved_total: number;
  active_match_id: number | null;
}

export interface StrategoSquadSlot {
  slot: string;
  role: StrategoRole;
  card: StrategoCard | null;
  eligible_positions: string[] | null;
}

export interface StrategoSquad {
  board_size: number;
  slots: string[];
  card_slots: StrategoSquadSlot[];
  /** slot -> [row, col]; row 0 = front row, row 1 = back row. */
  layout: Record<string, [number, number]>;
  is_complete: boolean;
  cards_needed: number;
  rarity_limits: { max_legendary: number; max_diamond: number; max_path?: number; min_rare: number; min_common: number };
  /** Highest rarity allowed on a Подкатчик slot. */
  tackler_max_rarity: Rarity;
  /** Highest rarity per capped role (tackler / provocateur / speedster). */
  role_max_rarity: Partial<Record<StrategoRole, Rarity>>;
  /** Rarity rules the current picks break; empty = valid. */
  violations: string[];
  options: StrategoCard[];
}

export interface StrategoInfo {
  board_size: number;
  wall_count: number;
  regular_count: number;
  tackler_count: number;
  speedster_count: number;
  move_limit: number;
  move_timeout_hours: number;
  challenge_expiry_hours: number;
  max_auto_moves: number;
  reward_win: number;
  reward_draw: number;
  reward_loss: number;
  daily_limit: number;
  rewarded_today: number;
  max_legendary: number;
  max_diamond: number;
  max_path?: number;
  min_rare: number;
  min_common: number;
  my_player_xp: number;
  tackler_max_rarity: Rarity;
  role_max_rarity?: Partial<Record<StrategoRole, Rarity>>;
  easy_reward_pct?: number;
  live_move_seconds?: number;
  skill_bonus_per_level?: number;
  puzzle_reward?: number;
}

export interface StrategoPiece {
  id: number;
  mine: boolean;
  row: number;
  col: number;
  hidden: boolean;
  revealed: boolean;
  moved: boolean;
  role: StrategoRole | null;
  power: number | null;
  card: StrategoCard | null;
}

export interface StrategoCombatPiece {
  id: number;
  mine: boolean;
  role: StrategoRole;
  power: number;
  card: StrategoCard | null;
}

export interface StrategoMove {
  ply: number;
  mine: boolean;
  piece_id: number;
  from_cell: [number, number];
  to_cell: [number, number];
  auto: boolean;
  combat: { attacker: StrategoCombatPiece; defender: StrategoCombatPiece; survivor: "attacker" | "defender" | "both" } | null;
}

export type StrategoMatchStatus = "pending_accept" | "in_progress" | "finished" | "declined" | "cancelled" | "expired";

export interface StrategoMatch {
  id: number;
  mode: "normal" | "puzzle" | "tutorial";
  difficulty: StrategoDifficulty | null;
  live: boolean;
  notes: Record<string, StrategoNoteTag>;
  blocked_move: [[number, number], [number, number]] | null;
  puzzle: StrategoPuzzleBrief | null;
  opponent_type: "bot" | "friend" | "online" | "chat";
  opponent_name: string;
  opponent_user_id: number | null;
  status: StrategoMatchStatus;
  viewer_side: "user" | "opponent";
  board_size: number;
  /** Impassable puddle cells, viewer coordinates. */
  lakes: [number, number][];
  move_limit: number;
  ply: number;
  my_turn: boolean;
  deadline: string | null;
  my_auto_moves: number;
  max_auto_moves: number;
  pieces: StrategoPiece[];
  lost_mine: StrategoCombatPiece[];
  lost_opponent: StrategoCombatPiece[];
  history: StrategoMove[];
  result: MatchResult | null;
  win_reason: "cup_captured" | "no_moves" | "move_limit" | "forfeit" | "timeout" | null;
  reward_coins: number;
  rating_delta: number;
  stake_coins: number;
  my_player_xp: number;
  my_strength: number | null;
  opponent_strength: number | null;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}

export interface StrategoStats {
  stratego_rating: number;
  stratego_rank: number | null;
}

export interface StrategoOpenChallengePreview {
  id: number;
  creator_name: string;
  stake_coins: number;
  status: StrategoMatchStatus;
  is_own_challenge: boolean;
}

export interface StrategoSearchStatus {
  status: "not_searching" | "searching" | "matched" | "timeout";
  match_id: number | null;
  created_at: string | null;
}

// ---------------------------------------------------------------------------
// «Футбольный магнат» (backend app/schemas/magnate.py)
// ---------------------------------------------------------------------------

export type MagnateMode = "bot" | "public" | "private";
export type MagnateStatus = "lobby" | "in_progress" | "finished" | "cancelled";
export type MagnatePhase = "roll" | "buy" | "end" | "moving" | "finished";
export type MagnateAction = "roll" | "buy" | "skip" | "build" | "end" | "pay_bail" | "use_card";
export type MagnateCellType =
  | "start" | "club" | "stadium" | "var" | "transfer" | "fine" | "jail" | "break" | "go_to_jail" | "chance" | "red_card";

export interface MagnateGroup {
  name: string;
  color: string;
}

export interface MagnateCell {
  index: number;
  type: MagnateCellType;
  name: string;
  group: number | null;
  price: number | null;
  /** base, 1–3 «Трибуны», «Арена» — clubs only */
  rent: number[] | null;
  build_cost: number | null;
  /** Crest abbreviation and [primary, secondary] colours (clubs). */
  short: string | null;
  colors: string[] | null;
  /** Fine cells with their own amount. */
  amount: number | null;
  owner_seat: number | null;
  level: number;
  current_rent: number;
}

export interface MagnatePlayer {
  seat: number;
  name: string;
  is_bot: boolean;
  is_me: boolean;
  left: boolean;
  cash: number;
  pos: number;
  in_jail: boolean;
  jail_cards: number;
  skip_turns: number;
  bankrupt: boolean;
  capital: number;
  missed: number;
  place: number | null;
  reward_coins: number;
}

export interface MagnateLogEntry {
  n: number;
  seat: number | null;
  text: string;
  kind: string;
}

export interface MagnateMatch {
  id: number;
  mode: MagnateMode;
  status: MagnateStatus;
  version: number;
  invite_code: string | null;
  is_creator: boolean;
  my_seat: number | null;
  seats_total: number;
  players: MagnatePlayer[];
  groups: MagnateGroup[];
  cells: MagnateCell[];
  turn: number | null;
  phase: MagnatePhase | null;
  my_turn: boolean;
  pending_cell: number | null;
  build_options: number[];
  can_pay_bail: boolean;
  can_use_card: boolean;
  jail_fine: number;
  stadium_rents: number[];
  round: number;
  max_rounds: number;
  turn_seconds: number;
  deadline: string | null;
  ends_at: string | null;
  lobby_deadline: string | null;
  server_now: string;
  last_roll: { seat: number; dice: number[]; n: number } | null;
  log: MagnateLogEntry[];
  finish_reason: string | null;
  my_place: number | null;
  my_reward: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface MagnateMatchBrief {
  id: number;
  mode: MagnateMode;
  status: MagnateStatus;
  players: number;
  my_place: number | null;
  reward_coins: number;
  left: boolean;
  created_at: string;
  finished_at: string | null;
}

export interface MagnateInfo {
  start_money: number;
  pass_start_bonus: number;
  jail_fine: number;
  fine_amount: number;
  max_rounds: number;
  time_limit_minutes: number;
  turn_seconds: number;
  max_missed_turns: number;
  lobby_wait_seconds: number;
  room_wait_minutes: number;
  place_rewards: number[];
  bot_reward_pct: number;
  daily_limit: number;
  rewarded_today: number;
  wins: number;
  active_match_id: number | null;
}

export interface MagnateRoomPreview {
  id: number;
  invite_code: string;
  creator_name: string;
  status: MagnateStatus;
  players: string[];
  seats_total: number;
  is_member: boolean;
}

// --- «Академия» ---------------------------------------------------------

export interface PathTask {
  id: number;
  metric: string;
  label: string;
  target: number;
  progress: number;
  applies: boolean;
  done: boolean;
}

export interface PathStage {
  index: number;
  name: string;
  min_rating: number;
  max_rating: number;
  talent_level: number;
  reached: boolean;
  current: boolean;
  tasks: PathTask[];
}

export interface PathTalentLevel {
  level: number;
  label: string;
  text: string;
  unlocked: boolean;
  unlock_stage: string | null;
}

export interface PathTalent {
  code: string;
  name: string;
  emoji: string;
  summary: string;
  kind: "static" | "dynamic";
  level: number;
  level_label: string | null;
  enabled: boolean;
  levels: PathTalentLevel[];
  modes: { mode: string; label: string; text: string | null }[];
}

export interface PathDaily {
  arena_free_total: number;
  arena_free_left: number;
  bought_attempts: number;
  career_total: number;
  career_left: number;
  ptour_total: number;
  ptour_left: number;
  coin_buys_left: number;
  next_coin_price: number | null;
  stars_buys_left: number;
  next_stars_price: number | null;
}

export interface PathHistoryItem {
  source_type: "arena" | "ptour" | "career";
  xp: number;
  result: "win" | "draw" | "loss" | null;
  goals: number;
  assists: number;
  levels: number[];
  stages: number[];
  created_at: string | null;
}

export interface PathState {
  card_id: number;
  title: string;
  enabled: boolean;
  player_name: string;
  position: string;
  base_rating: number;
  rating: number;
  ceiling: number;
  level: number;
  max_level: number;
  xp: number;
  xp_into_level: number;
  xp_for_next: number | null;
  blocked_by_tasks: boolean;
  stage: number;
  stage_name: string;
  is_legend: boolean;
  stages: PathStage[];
  talent: PathTalent | null;
  daily: PathDaily;
  xp_rules: { match: number; win: number; draw: number; goal: number; assist: number };
  totals: Record<string, number>;
  hunger_streak: number;
  recent: PathHistoryItem[];
  prestige?: PathPrestige;
  /** «Академия» building bonuses applied to this card. */
  academy?: { xp_pct: number; attempts: number; task_cut_pct: number };
}

export interface PathPrestigeReward {
  coins: number;
  attempts: number;
  skill_tokens: number;
}

export interface PathPrestige {
  tier: number;
  max_tier: number;
  tier_name: string | null;
  names: string[];
  next_dupes: number | null;
  ratio: number;
  free_units: number;
  next_coins: number | null;
  next_reward: PathPrestigeReward | null;
  free_duplicates: { id: number; serial_number: number; skill_code: string | null; player_name: string; same_player: boolean; units: number }[];
  xp_bonus_pct: number;
  next_xp_bonus_pct: number | null;
  extra_free_attempts: number;
  sell_price: number;
  icon_number: number | null;
  reforged: boolean;
  can_reforge: boolean;
  reforge_options: { code: string; name: string; emoji: string; summary: string }[];
}

export interface PathCatalog {
  title: string;
  enabled: boolean;
  talent_cap: number;
  stages: { index: number; name: string; max_rating: number; talent_level: number }[];
  talents: PathTalent[];
}

export interface MatchTalentNote {
  code: string;
  name: string;
  emoji: string;
  level: number;
  level_label: string;
  player: string | null;
  bonus: number;
  aura?: boolean;
}

export interface PathMatchProgress {
  user_card_id: number;
  status: "awarded" | "duplicate" | "no_attempts" | "limit" | "not_path";
  xp: number;
  levels: number[];
  stages: number[];
}

// --- «Академия» building ---------------------------------------------------

export interface AcademyWing {
  code: "scout" | "training" | "dorm" | "staff" | "hall";
  name: string;
  emoji: string;
  about: string;
  level: number;
  max_level: number;
  effect: string | null;
  next_effect: string | null;
  next_cost: number | null;
  next_hours: number | null;
  building: boolean;
}

export interface AcademyState {
  enabled: boolean;
  level: number;
  max_level: number;
  wings: AcademyWing[];
  construction: { building_code: string; to_level: number; ends_at: string; remaining_seconds: number; speedup_stars: number } | null;
  scout_report: { chance_pct: number; consolation_coins: number; cooldown_days: number; available: boolean; next_at: string | null } | null;
  effects: Record<string, number>;
  showcase_slots: number;
  academy_cards: number;
  cards: UserCard[];
  new_balance?: number;
  report?: { coins?: number; card_id?: number; player_name?: string } | null;
}

// «Клубная база» (GET /club-base) — see backend club_base_service.state_out.
export type ClubBaseCode =
  | "hq" | "stadium" | "hotel" | "training" | "medical" | "analytics" | "media" | "marketing" | "shop" | "accounting";

export interface ClubBaseBuilding {
  code: ClubBaseCode;
  name: string;
  emoji: string;
  about: string;
  group: "core" | "finance";
  level: number;
  max_level: number;
  cap_level: number;
  effects: string[];
  next_effects: string[];
  next_cost: number | null;
  next_cost_full: number | null;
  next_hours: number | null;
  locked: boolean;
  building: boolean;
}

export interface ClubBaseLook {
  seats: string;
  roof: "none" | "canopy" | "full";
  lights: "on" | "off";
  screen: "on" | "off";
  pitch: "stripes" | "checks" | "diagonal";
  facade: "concrete" | "brick" | "glass" | "gold";
}

/** A stadium cosmetics shop item (GameConfig.club_base_cosmetics). */
export interface ClubBaseCosmetic {
  code: string;
  kind: keyof ClubBaseLook;
  value: string;
  name: string;
  coins: number;
  stars: number;
  min_level: number;
  owned: boolean;
  free: boolean;
  usable: boolean;
}

export interface ClubBaseState {
  enabled: boolean;
  level: number;
  max_level: number;
  academy_level: number;
  academy_max_level: number;
  total_level: number;
  buildings: ClubBaseBuilding[];
  construction: {
    owner: "base" | "academy";
    building_code: string;
    name: string;
    emoji: string;
    to_level: number;
    ends_at: string;
    remaining_seconds: number;
    speedup_stars: number;
  } | null;
  income: { daily: number; pending: number; cap: number; max_days: number };
  stadium: {
    level: number;
    capacity: number;
    matchday_income: number;
    look: ClubBaseLook;
    defaults: ClubBaseLook;
    cosmetics: ClubBaseCosmetic[];
  };
  effects: Record<string, number>;
  art: { background: string | null; buildings: Partial<Record<ClubBaseCode, string>> };
  new_balance?: number;
  claimed?: number;
}

// --- «Мордобой» ---

export type MordoboiAction = "jab" | "hook" | "uppercut" | "block" | "dodge";
/** Per side, what happened to its own action in the exchange. */
export type MordoboiOutcome = "landed" | "beaten" | "blocked" | "slipped" | "caught" | "counter" | "none";
export type MordoboiMatchStatus = "pending_accept" | "in_progress" | "finished" | "declined" | "cancelled" | "expired";
export type MordoboiOpponentType = "bot" | "friend" | "online" | "chat";

export interface MordoboiCard {
  user_card_id: number | null;
  player_id: number;
  display_name: string;
  position: string;
  image_path: string | null;
  rarity: string;
  rating: number;
}

export interface MordoboiBoxerStats {
  power: number;
  speed: number;
  guard: number;
  max_hp: number;
  max_stamina: number;
}

export interface MordoboiBoxerOption {
  card: MordoboiCard;
  stats: MordoboiBoxerStats;
}

export interface MordoboiBoxer {
  selected: MordoboiBoxerOption | null;
  options: MordoboiBoxerOption[];
  look: MordoboiLook;
  nickname_options: string[];
}

export interface MordoboiLegend {
  code: string;
  name: string;
  nickname: string;
  tagline: string;
  position: string;
  rating: number;
  reward: number;
  beaten_today: boolean;
  wins_total: number;
  active_match_id: number | null;
  look: MordoboiLook;
}

export interface MordoboiClubRing {
  active: boolean;
  my_club: string | null;
  opponent_club: string | null;
  ends_at: string | null;
  win_points: number;
  member_cap: number;
  my_points: number;
  my_club_points: number;
  opponent_club_points: number;
  opponents: { user_id: number; name: string }[];
}

/** «Выход на ринг»: style keys of the equipped ring cosmetics. */
export interface MordoboiLook {
  nickname: string | null;
  gloves: string | null;
  shorts: string | null;
  entrance: string | null;
}

export interface MordoboiFighter extends MordoboiBoxerStats {
  name: string;
  card: MordoboiCard | null;
  look: MordoboiLook;
  hp: number;
  stamina: number;
  landed: number;
  damage_dealt: number;
}

export interface MordoboiExchange {
  n: number;
  round: number;
  exchange: number;
  my_action: MordoboiAction;
  opponent_action: MordoboiAction;
  my_outcome: MordoboiOutcome;
  opponent_outcome: MordoboiOutcome;
  my_damage: number;
  opponent_damage: number;
  my_hp: number;
  opponent_hp: number;
  my_auto: boolean;
  opponent_auto: boolean;
  round_end: boolean;
  end: string | null;
}

export interface MordoboiMatch {
  id: number;
  version: number;
  mode: "normal" | "legend";
  legend_tagline: string | null;
  opponent_type: MordoboiOpponentType;
  opponent_name: string;
  opponent_user_id: number | null;
  status: MordoboiMatchStatus;
  viewer_side: "user" | "opponent";
  difficulty: string | null;
  live: boolean;
  rounds: number;
  exchanges_per_round: number;
  round: number;
  exchange: number;
  me: MordoboiFighter | null;
  opponent: MordoboiFighter | null;
  my_pick: MordoboiAction | null;
  opponent_ready: boolean;
  can_pick: boolean;
  available_actions: MordoboiAction[];
  deadline: string | null;
  my_auto_moves: number;
  max_auto_moves: number;
  log: MordoboiExchange[];
  scorecards: { mine: number; opponent: number }[];
  result: "win" | "draw" | "loss" | null;
  win_reason: string | null;
  reward_coins: number;
  rating_delta: number;
  stake_coins: number;
  brutality: MordoboiBrutality | null;
  can_brutality: boolean;
  created_at: string;
  expires_at: string | null;
  resolved_at: string | null;
}

export interface MordoboiBrutality {
  by_me: boolean;
  style_key: string;
  name: string;
  emoji: string;
  image_path: string | null;
  bonus_coins: number;
  /** The beaten side's «Каска» bounced it back onto the winner. */
  reflected: boolean;
  /** From the viewer's side: «надел ему труханы на голову» / «…тебе…». */
  text: string;
}

export interface MordoboiOpenChallengePreview {
  id: number;
  creator_name: string;
  stake_coins: number;
  status: MordoboiMatchStatus;
  is_own_challenge: boolean;
}

export interface MordoboiInfo {
  enabled: boolean;
  rounds: number;
  exchanges_per_round: number;
  base_hp: number;
  reward_win: number;
  reward_draw: number;
  reward_loss: number;
  reward_ko_bonus: number;
  daily_limit: number;
  rewarded_today: number;
  easy_reward_pct: number;
  move_timeout_hours: number;
  live_move_seconds: number;
  challenge_expiry_hours: number;
  max_auto_moves: number;
  stamina_cost: Record<MordoboiAction, number>;
  damage: Partial<Record<MordoboiAction, number>>;
  legend_reward: number;
}

export interface MordoboiStats {
  mordoboi_rating: number;
  mordoboi_rank: number | null;
}

export interface MordoboiSearchStatus {
  status: "not_searching" | "searching" | "matched" | "timeout";
  match_id: number | null;
}

// --- «Контратака» ---

export type KontraTier = "common" | "rare" | "epic" | "legendary" | "diamond" | "path" | "my_player";

export interface KontraCard {
  card_id: number;
  display_name: string;
  position: string;
  rarity: string;
  rating: number;
  image_path: string | null;
  tier: KontraTier;
}

export interface KontraAbility {
  code: string;
  name: string;
  description: string;
  cooldown: number;
  cd: number;
  ready: boolean;
}

export interface KontraPassive {
  code: string;
  name: string;
  description: string;
}

export interface KontraFighter {
  card: KontraCard;
  role: string;
  role_label: string;
  hp: number;
  atk: number;
  defence: number;
  spd: number;
  abilities: KontraAbility[];
  passive: KontraPassive | null;
  gear_count: number;
}

export interface KontraSquad {
  fighters: KontraFighter[];
  leader_id: number | null;
  power: number;
  chemistry_pct: number;
  chemistry_label: string | null;
  leader_aura: string | null;
  options: KontraFighter[];
  size: number;
}

export interface KontraUnit {
  id: string;
  side: "me" | "foe";
  name: string;
  card: KontraCard | null;
  role: string;
  tier: string;
  hp: number;
  max_hp: number;
  meter_pct: number;
  alive: boolean;
  leader: boolean;
  effects: { code: string; label: string; turns: number }[];
  abilities: KontraAbility[];
  passive: KontraPassive | null;
}

export interface KontraEvent {
  kind: "ability" | "hit" | "miss" | "heal" | "down" | "effect" | "meter" | "tick" | "stunned" | "turn" | "passive" | "end";
  n: number;
  actor?: string;
  target?: string;
  ability?: string;
  name?: string;
  damage?: number;
  absorbed?: number;
  crit?: boolean;
  hp?: number;
  amount?: number;
  effect?: string;
  winner?: string;
}

export interface KontraGear {
  id: number;
  slot: string;
  slot_label: string;
  set_code: string;
  set_name: string;
  rarity: string;
  rarity_label: string;
  stat: string;
  pct: number;
  card_id: number | null;
}

export interface KontraBattle {
  id: number;
  version: number;
  mode: "arena" | "boss";
  status: "in_progress" | "finished";
  result: "win" | "loss" | null;
  opponent_name: string;
  manual: boolean;
  auto: boolean;
  turn_of: string | null;
  can_act: boolean;
  round: number;
  max_rounds: number;
  units: KontraUnit[];
  events: KontraEvent[];
  damage: number;
  reward_coins: number;
  rating_delta: number;
  gear_drop: KontraGear | null;
  boss_name: string | null;
  boss_tagline: string | null;
  created_at: string;
}

export interface KontraOffer {
  index: number;
  name: string;
  rating: number;
  power: number;
  is_bot: boolean;
  cards: KontraCard[];
}

export interface KontraArena {
  rating: number;
  rank: number | null;
  offers: KontraOffer[];
  rewarded_today: number;
  daily_limit: number;
  reward_win: number;
  reward_loss: number;
  rating_win: number;
  rating_loss: number;
}

export interface KontraBoss {
  code: string;
  name: string;
  tagline: string;
  week_start: string;
  week_hp: number;
  week_damage: number;
  phase: number;
  my_damage: number;
  my_best: number;
  club_name: string | null;
  club_damage: number;
  attempts_left: number;
  attempts_per_day: number;
  reward_tiers: [number, number][];
  top: { user_id: number; name: string; damage: number }[];
}

export interface KontraHub {
  enabled: boolean;
  squad_ready: boolean;
  rating: number;
  active_battle_id: number | null;
  boss_name: string;
  boss_attempts_left: number;
  gear_count: number;
}

export interface KontraGearList {
  items: KontraGear[];
  sets: { code: string; name: string; description: string }[];
  chest_coins: number;
  chest_stars: number;
  balance: number;
}

/** «Топ недели»: one place taken in one ranking (a popup each). */
export interface WeeklyTopAward {
  id: number;
  week_start: string;
  metric: RankingMetric;
  metric_label: string;
  rank: number;
  value: number;
  coins: number;
  pack_name: string | null;
  cards: number;
  cosmetic_name: string | null;
  cosmetic_style: string | null;
  balance: number;
}

export interface WeeklyTopPlace {
  rank: number;
  coins: number;
  pack_name: string | null;
  cosmetic_name: string | null;
  cosmetic_style: string | null;
}

export interface WeeklyTopHall {
  week_start: string | null;
  winners: { rank: number; user_id: number; display_name: string; value: number; cosmetic_style: string | null }[];
}

export interface WeeklyTopInfo {
  enabled: boolean;
  size: number;
  ends_at: string;
  places: WeeklyTopPlace[];
  metrics: RankingMetric[];
  starting_values: Partial<Record<RankingMetric, number>>;
}

/** «Карты за звёзды»: a footballer card on sale for Telegram Stars. */
export interface CardOffer {
  id: number;
  player: Player;
  stars_price: number;
  title: string | null;
  ends_at: string | null;
  stock: number | null;
  left: number | null;
  per_user_limit: number;
  bought: number;
  can_buy: boolean;
  retired: boolean;
}

export interface CardOfferAdminInput {
  player_id: number;
  stars_price: number;
  title: string | null;
  starts_at: string | null;
  ends_at: string | null;
  stock: number | null;
  per_user_limit: number;
  is_active: boolean;
  sort_order: number;
}

export interface CardOfferAdmin extends Omit<CardOfferAdminInput, "player_id"> {
  id: number;
  player: Player;
  sold_count: number;
  live: boolean;
  announced_at: string | null;
  stars_total: number;
  buyers: number;
  viewers: number;
}

// «Путь дебютанта» (GET /newbie)
export interface NewbieTask {
  code: string;
  label: string;
  path: string;
  coins: number;
  pack_name: string | null;
  played: boolean;
  claimed: boolean;
}

export interface NewbieGift {
  day: number;
  coins: number;
  card_rarity: Rarity | null;
  opens_on: string;
  ready: boolean;
  claimed: boolean;
}

export interface NewbieState {
  active: boolean;
  day: number;
  first_pack_done: boolean;
  first_pack_top: Rarity | null;
  squad_pack_done: boolean;
  squad_size: number;
  arena_played: boolean;
  arena_claimed: boolean;
  arena_rarity: Rarity | null;
  tasks: NewbieTask[];
  gifts: NewbieGift[];
  bound_days: number;
  steps_done: number;
  steps_total: number;
  /** Every step done: «Путь пройден» with its reward. */
  finale_ready?: boolean;
  finale?: RewardBundle | null;
}

export interface NewbieClaimResult {
  rewards: GrantedRewards;
  state: NewbieState;
}

export interface NewbieFunnel {
  days: number;
  started: number;
  completed: number;
  steps: { code: string; label: string; players: number }[];
}
