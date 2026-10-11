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
}

export interface LifestyleCatalog {
  categories: { code: LifestyleCategory; label: string }[];
  items: LifestyleItem[];
  prestige: number;
  balance: number;
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
