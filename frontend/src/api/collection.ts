import { api } from "@/lib/api";
import type { CollectionStats, Page, UserCard } from "@/types";

export interface CollectionFilters {
  rarity?: string;
  country?: string;
  club?: string;
  position?: string;
  min_rating?: number;
  max_rating?: number;
  collection_id?: number;
  search?: string;
  sort_by?: "rating" | "rarity" | "acquired_at";
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export async function fetchCollection(filters: CollectionFilters): Promise<Page<UserCard>> {
  const { data } = await api.get<Page<UserCard>>("/collection/cards", { params: filters });
  return data;
}

export async function fetchUserCollection(userId: number, filters: CollectionFilters = {}): Promise<Page<UserCard>> {
  const { data } = await api.get<Page<UserCard>>(`/users/${userId}/collection`, { params: filters });
  return data;
}

export async function fetchCollectionStats(): Promise<CollectionStats> {
  const { data } = await api.get<CollectionStats>("/collection/stats");
  return data;
}

export async function sellCard(userCardId: number, confirmLastCopy = false) {
  const { data } = await api.post("/collection/cards/sell", {
    user_card_id: userCardId,
    confirm_last_copy: confirmLastCopy,
  });
  return data as { sold_count: number; coins_earned: number; new_balance: number };
}

export async function bulkSellCards(userCardIds: number[], confirmLastCopy = false) {
  const { data } = await api.post("/collection/cards/bulk-sell", {
    user_card_ids: userCardIds,
    confirm_last_copy: confirmLastCopy,
  });
  return data as { sold_count: number; coins_earned: number; new_balance: number };
}

export async function setCardHiddenFromTrade(userCardId: number, hidden: boolean): Promise<UserCard> {
  const { data } = await api.patch<UserCard>(`/collection/cards/${userCardId}/hidden`, { hidden });
  return data;
}
