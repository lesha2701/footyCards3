import { api } from "@/lib/api";

/** The same attack/defense pair every card in the game has. */
export type MyPlayerAttr = "atk" | "def";
export type MyPlayerTier = "bronze" | "silver" | "gold" | "legend";

export interface MyPlayerAppearance {
  skin: number;
  hair: number;
  hair_color: number;
  beard: number;
  eye_color: number;
  kit: number;
  kit_pattern: number;
}

export interface MyPlayer {
  name: string;
  number: number;
  position: string;
  category: "GK" | "DEF" | "MID" | "FWD";
  appearance: MyPlayerAppearance;
  attributes: Record<MyPlayerAttr, number>;
  rating: number;
  attack_rating: number;
  defense_rating: number;
  tier: MyPlayerTier;
  tier_label: string;
  /** The attribute that matters most at this position. */
  key_attr: MyPlayerAttr;
  /** Equipped cosmetics (codes from the shop catalog). */
  accessory?: string | null;
  background?: string | null;
  /** Card effect (fx_sparkle | fx_fire | fx_lightning). */
  effect?: string | null;
  /** National team. */
  country?: string | null;
}

export type MyPlayerCosmeticKind = "accessory" | "background" | "effect" | "hair";
export type MyPlayerDrill = "shot" | "pass" | "tackle" | "save";

export interface MyPlayerTrophy {
  id: number;
  code: string;
  name: string;
  icon: string;
  image_path: string | null;
  message: string | null;
  granted_at: string;
}

export interface MyPlayerAttention {
  create: boolean;
  level_up: boolean;
  points: boolean;
  training: boolean;
  income: boolean;
  career_offers: boolean;
}

export interface MyPlayerSkillOption {
  code: string;
  name: string;
  icon: string;
  effect: string;
  bonus_phrase: string;
}

/** Skill of «Мой игрок» — bought and leveled exactly like a card skill
 * (tokens + coins at the card-skill prices from the admin panel). */
export interface MyPlayerSkill {
  /** The card-skill mechanic is on. */
  enabled: boolean;
  code: string | null;
  name: string | null;
  icon: string | null;
  /** 0 = no skill yet. */
  level: number;
  level_label: string | null;
  upgrade: { to_level: number; token_cost: number; coin_cost: number } | null;
  assign_token_cost: number;
  assign_coin_cost: number;
  replace_token_cost: number;
  replace_coin_cost: number;
  /** Skill-token balance by skill code. */
  tokens: Record<string, number>;
  options: MyPlayerSkillOption[];
}

export interface MyPlayerCosmeticItem {
  code: string;
  kind: MyPlayerCosmeticKind;
  name: string;
  /** Coins / Telegram Stars; 0 = not sold for that currency. */
  price: number;
  stars_price: number;
  owned: boolean;
  /** «Статус» the item adds (premium style items). */
  status?: number;
  /** Premium hairstyle: the appearance hair index it sets. */
  hair_index?: number | null;
}

export interface MyPlayerLeaderboardEntry {
  rank: number;
  user_id: number;
  is_me: boolean;
  user_name: string;
  level: number;
  player: MyPlayer;
}

export interface MyPlayerView {
  enabled: boolean;
  /** Coin balance, to refresh the top bar after a purchase. */
  balance: number;
  player: MyPlayer | null;
  xp: number;
  level: number;
  xp_into_level: number;
  xp_for_next: number;
  xp_today: number;
  xp_daily_cap: number;
  xp_per_reward: number;
  xp_career_match: number;
  xp_stratego_match: number;
  xp_player_career_match: number;
  /** XP bonus from «Имущество», percent. */
  xp_bonus_pct: number;
  points_available: number;
  points_per_level: number;
  level_seen: number;
  /** Set until the level-up screen is acknowledged. */
  level_up: { from_level: number; to_level: number; points: number } | null;
  rating_cap: number;
  at_rating_cap: boolean;
  tier_thresholds: number[];
  appearance_options: Record<keyof MyPlayerAppearance, number>;
  attr_labels: Record<MyPlayerAttr, string>;
  next_tier_at: number | null;
  skill: MyPlayerSkill | null;
  training: {
    /** The free daily run is used up. */
    done_today: boolean;
    /** A run can start now (free one left, or a bought credit). */
    can_train: boolean;
    extra_credits: number;
    extra_bought_today: number;
    extra_max: number;
    extra_left_today: number;
    extra_coins_price: number;
    extra_stars_price: number;
    xp_base: number;
    xp_per_hit: number;
    max_hits: number;
    /** Today's drill — follows the weekday and the player's line. */
    drill: { code: MyPlayerDrill; name: string; hint: string };
    /** Free trainings in a row; every streak_days pays streak_tokens skill tokens. */
    streak: number;
    streak_days: number;
    streak_tokens: number;
    streak_left: number;
    freshness_bonus: number;
  };
  cosmetics: {
    owned: string[];
    accessory: string | null;
    background: string | null;
    effect: string | null;
    hair: string | null;
    catalog: MyPlayerCosmeticItem[];
  };
  freshness: {
    value: number;
    /** Rating points lost in matches right now. */
    penalty: number;
    max_penalty: number;
    regen_per_hour: number;
    regen_bonus: number;
    per_match: number;
    training: number;
  } | null;
  role_change: { coins_price: number; stars_price: number } | null;
  trophies: MyPlayerTrophy[];
  /** What the top-bar dot is for. */
  attention: MyPlayerAttention;
  /** Countries the player can represent. */
  countries: string[];
  /** Only on the training-finish response. */
  training_xp?: number | null;
  streak_reward?: { tokens: number; skill_code: string; skill_name: string; skill_icon: string; streak: number } | null;
}

export interface MyPlayerDraft {
  name: string;
  number: number;
  position: string;
  appearance: MyPlayerAppearance;
  country?: string | null;
}

export async function fetchMyPlayer(): Promise<MyPlayerView> {
  const { data } = await api.get<MyPlayerView>("/my-player");
  return data;
}

export async function createMyPlayer(draft: MyPlayerDraft): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player", draft);
  return data;
}

export async function updateMyPlayer(patch: Partial<MyPlayerDraft>): Promise<MyPlayerView> {
  const { data } = await api.patch<MyPlayerView>("/my-player", patch);
  return data;
}

export async function trainMyPlayer(attr: MyPlayerAttr, points: number): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player/train", { attr, points });
  return data;
}

export interface MyPlayerPublic {
  player: MyPlayer | null;
  level: number | null;
  trophies: MyPlayerTrophy[];
}

export async function fetchPublicMyPlayer(userId: number): Promise<MyPlayerPublic> {
  const { data } = await api.get<MyPlayerPublic>(`/my-player/users/${userId}`);
  return data;
}

export async function setMyPlayerSkill(code: string): Promise<MyPlayerView> {
  const { data } = await api.put<MyPlayerView>("/my-player/skill", { code });
  return data;
}

export async function startMyPlayerTraining(): Promise<{ max_hits: number; min_seconds: number; drill: MyPlayerDrill }> {
  const { data } = await api.post<{ max_hits: number; min_seconds: number; drill: MyPlayerDrill }>("/my-player/training/start");
  return data;
}

export async function finishMyPlayerTraining(hits: number): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player/training/finish", { hits });
  return data;
}

export async function buyMyPlayerCosmetic(code: string): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player/cosmetics/buy", { code });
  return data;
}

export async function equipMyPlayerCosmetic(kind: MyPlayerCosmeticKind, code: string | null): Promise<MyPlayerView> {
  const { data } = await api.put<MyPlayerView>("/my-player/cosmetics/equip", { kind, code });
  return data;
}

export async function fetchMyPlayerLeaderboard(
  scope: "all" | "friends",
): Promise<{ scope: string; entries: MyPlayerLeaderboardEntry[]; me: MyPlayerLeaderboardEntry | null }> {
  const { data } = await api.get(`/my-player/leaderboard`, { params: { scope } });
  return data;
}

export async function upgradeMyPlayerSkill(): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player/skill/upgrade");
  return data;
}

export async function buyExtraTraining(): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player/extra-training/buy");
  return data;
}

export interface MyPlayerStarsInvoice {
  invoice_link: string;
  payload_token: string;
  stars_amount: number;
}

export type MyPlayerStarsPurchase =
  | { purchase: "training" }
  | { purchase: "item"; itemId: number }
  | { purchase: "cosmetic"; code: string }
  | { purchase: "role"; position: string };

export async function createMyPlayerStarsInvoice(order: MyPlayerStarsPurchase): Promise<MyPlayerStarsInvoice> {
  const { data } = await api.post<MyPlayerStarsInvoice>("/my-player/stars-invoice", {
    purchase: order.purchase,
    item_id: order.purchase === "item" ? order.itemId : null,
    code: order.purchase === "cosmetic" ? order.code : null,
    position: order.purchase === "role" ? order.position : null,
  });
  return data;
}

export async function fetchMyPlayerStarsInvoiceStatus(
  payloadToken: string,
): Promise<{ status: "pending" | "completed"; my_player_result?: { kind: string; name?: string } | null }> {
  const { data } = await api.get(`/my-player/stars-invoices/${payloadToken}`);
  return data;
}

export async function ackMyPlayerLevelUp(): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player/level-seen");
  return data;
}

export async function changeMyPlayerRole(position: string): Promise<MyPlayerView> {
  const { data } = await api.post<MyPlayerView>("/my-player/role", { position });
  return data;
}

export interface MyPlayerDuelSide extends MyPlayer {
  /** Rating as fielded in the duel (fatigue included). */
  match_rating: number | null;
}

export interface MyPlayerDuel {
  id: number;
  created_at: string;
  as_challenger: boolean;
  opponent_user_id: number;
  opponent_name: string;
  my_goals: number;
  opp_goals: number;
  result: "win" | "draw" | "loss";
  reward_coins: number;
  events: { n: number; side: "me" | "opp"; outcome: "goal" | "save" | "miss" }[];
  me: MyPlayerDuelSide | null;
  opp: MyPlayerDuelSide | null;
}

export interface MyPlayerDuels {
  enabled: boolean;
  left_today: number;
  per_day: number;
  reward_win: number;
  reward_draw: number;
  xp: number;
  attacks: number;
  friends: { user_id: number; user_name: string; level: number; player: MyPlayer }[];
  recent: MyPlayerDuel[];
}

export async function fetchMyPlayerDuels(): Promise<MyPlayerDuels> {
  const { data } = await api.get<MyPlayerDuels>("/my-player/duels");
  return data;
}

export async function playMyPlayerDuel(opponentUserId: number): Promise<{ duel: MyPlayerDuel; duels: MyPlayerDuels; balance: number }> {
  const { data } = await api.post<{ duel: MyPlayerDuel; duels: MyPlayerDuels; balance: number }>("/my-player/duels", {
    opponent_user_id: opponentUserId,
  });
  return data;
}
