import { api } from "@/lib/api";
import type {
  CardUpgradeResult,
  CardUpgradeRule,
  CollectionStats,
  DiamondMaterialCardsOut,
  DiamondUpgradeTier,
  FeedCardsResult,
  Page,
  Rarity,
  UserCard,
} from "@/types";

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

export async function fetchUpgradeRules(): Promise<CardUpgradeRule[]> {
  const { data } = await api.get<CardUpgradeRule[]>("/collection/upgrade-rules");
  return data;
}

// Every individual unlocked card of `rarity` — NOT deduplicated by player,
// unlike fetchCollection, since each owned copy is its own stakeable unit.
export async function fetchUpgradeableCards(rarity: Rarity): Promise<UserCard[]> {
  const { data } = await api.get<UserCard[]>("/collection/upgrade-cards", { params: { rarity } });
  return data;
}

export async function upgradeCards(
  userCardIds: number[],
  toRarity: Rarity,
  idempotencyKey?: string
): Promise<CardUpgradeResult> {
  const { data } = await api.post<CardUpgradeResult>("/collection/upgrade", {
    user_card_ids: userCardIds,
    to_rarity: toRarity,
    idempotency_key: idempotencyKey,
  });
  return data;
}

export async function fetchDiamondUpgradeTiers(): Promise<DiamondUpgradeTier[]> {
  const { data } = await api.get<DiamondUpgradeTier[]>("/collection/diamond-upgrade-tiers");
  return data;
}

export async function fetchDiamondUpgradeCap(): Promise<number> {
  const { data } = await api.get<{ cap: number }>("/collection/diamond-upgrade-cap");
  return data.cap;
}

export async function fetchDiamondMaterialCards(diamondCardId: number): Promise<DiamondMaterialCardsOut> {
  const { data } = await api.get<DiamondMaterialCardsOut>("/collection/diamond-upgrade/material-cards", {
    params: { diamond_card_id: diamondCardId },
  });
  return data;
}

export async function feedDiamondCard(diamondCardId: number, materialCardIds: number[]): Promise<FeedCardsResult> {
  const { data } = await api.post<FeedCardsResult>("/collection/diamond-upgrade/feed", {
    diamond_card_id: diamondCardId,
    material_card_ids: materialCardIds,
  });
  return data;
}
