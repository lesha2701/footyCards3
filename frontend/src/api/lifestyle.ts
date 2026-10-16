import { api } from "@/lib/api";

export type LifestyleCategory = "car" | "estate" | "stocks" | "other";

export interface LifestyleItem {
  id: number;
  name: string;
  description: string;
  category: LifestyleCategory;
  emoji: string;
  image_path: string | null;
  coins_price: number;
  stars_price: number;
  prestige: number;
  max_supply: number | null;
  sold_count: number;
  sold_out: boolean;
  owned: boolean;
  serial_number: number | null;
  /** none | freshness_regen | xp_bonus_pct | weekly_income */
  effect: LifestyleEffect;
  effect_value: number;
  effect_label: string;
  /** weekly_income: coins ready to claim on this item. */
  income_ready: number;
  next_income_at: string | null;
}

export type LifestyleEffect = "none" | "freshness_regen" | "xp_bonus_pct" | "weekly_income";

export interface LifestyleCatalog {
  categories: { code: LifestyleCategory; label: string }[];
  items: LifestyleItem[];
  prestige: number;
  balance: number;
  /** Effects summed over everything owned. */
  effects: { effect: LifestyleEffect; value: number; label: string }[];
  income_ready: number;
  claimed?: number | null;
}

export async function fetchLifestyle(): Promise<LifestyleCatalog> {
  const { data } = await api.get<LifestyleCatalog>("/lifestyle");
  return data;
}

export async function buyLifestyleWithCoins(itemId: number): Promise<LifestyleCatalog> {
  const { data } = await api.post<LifestyleCatalog>(`/lifestyle/${itemId}/buy`);
  return data;
}

export async function fetchPublicLifestyle(userId: number): Promise<{ items: LifestyleItem[]; prestige: number }> {
  const { data } = await api.get<{ items: LifestyleItem[]; prestige: number }>(`/lifestyle/users/${userId}`);
  return data;
}

export async function claimLifestyleIncome(): Promise<LifestyleCatalog> {
  const { data } = await api.post<LifestyleCatalog>("/lifestyle/income/claim");
  return data;
}
