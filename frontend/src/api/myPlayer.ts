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
  kind: "accessory" | "background";
  name: string;
  price: number;
  owned: boolean;
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
  points_available: number;
  points_per_level: number;
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
  };
  cosmetics: { owned: string[]; accessory: string | null; background: string | null; catalog: MyPlayerCosmeticItem[] };
  /** Only on the training-finish response. */
  training_xp?: number | null;
}

export interface MyPlayerDraft {
  name: string;
  number: number;
  position: string;
  appearance: MyPlayerAppearance;
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

export async function fetchPublicMyPlayer(userId: number): Promise<{ player: MyPlayer | null; level: number | null }> {
  const { data } = await api.get<{ player: MyPlayer | null; level: number | null }>(`/my-player/users/${userId}`);
  return data;
}

export async function setMyPlayerSkill(code: string): Promise<MyPlayerView> {
  const { data } = await api.put<MyPlayerView>("/my-player/skill", { code });
  return data;
}

export async function startMyPlayerTraining(): Promise<{ max_hits: number; min_seconds: number }> {
  const { data } = await api.post<{ max_hits: number; min_seconds: number }>("/my-player/training/start");
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

export async function equipMyPlayerCosmetic(kind: "accessory" | "background", code: string | null): Promise<MyPlayerView> {
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

export async function createMyPlayerStarsInvoice(purchase: "training" | "item", itemId?: number): Promise<MyPlayerStarsInvoice> {
  const { data } = await api.post<MyPlayerStarsInvoice>("/my-player/stars-invoice", { purchase, item_id: itemId ?? null });
  return data;
}

export async function fetchMyPlayerStarsInvoiceStatus(
  payloadToken: string,
): Promise<{ status: "pending" | "completed"; my_player_result?: { kind: string; name?: string } | null }> {
  const { data } = await api.get(`/my-player/stars-invoices/${payloadToken}`);
  return data;
}
