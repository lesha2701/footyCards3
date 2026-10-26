import { api } from "@/lib/api";
import type {
  CardStarOperation,
  CardStarState,
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
  /** true = only copies with a skill, false = only without. */
  has_skill?: boolean;
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

export async function sellCard(userCardId: number, confirmLastCopy = false, confirmSkillLoss = false) {
  const { data } = await api.post("/collection/cards/sell", {
    user_card_id: userCardId,
    confirm_last_copy: confirmLastCopy,
    confirm_skill_loss: confirmSkillLoss,
  });
  return data as { sold_count: number; coins_earned: number; new_balance: number };
}

export async function bulkSellCards(userCardIds: number[], confirmLastCopy = false, confirmSkillLoss = false) {
  const { data } = await api.post("/collection/cards/bulk-sell", {
    user_card_ids: userCardIds,
    confirm_last_copy: confirmLastCopy,
    confirm_skill_loss: confirmSkillLoss,
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
export interface UpgradeCardsQuery {
  position?: string | null;
  country?: string | null;
  club?: string | null;
  limit?: number;
  offset?: number;
}

/** One page of the Forge list (strongest first), filtered on the server. */
export async function fetchUpgradeableCards(rarity: Rarity, query: UpgradeCardsQuery = {}): Promise<UserCard[]> {
  const params = Object.fromEntries(Object.entries({ rarity, ...query }).filter(([, v]) => v != null && v !== ""));
  const { data } = await api.get<UserCard[]>("/collection/upgrade-cards", { params });
  return data;
}

export async function upgradeCards(
  userCardIds: number[],
  toRarity: Rarity,
  idempotencyKey?: string,
  confirmSkillLoss = false,
  confirmLeaveSquad = false,
): Promise<CardUpgradeResult> {
  const { data } = await api.post<CardUpgradeResult>("/collection/upgrade", {
    user_card_ids: userCardIds,
    to_rarity: toRarity,
    idempotency_key: idempotencyKey,
    confirm_skill_loss: confirmSkillLoss,
    confirm_leave_squad: confirmLeaveSquad,
  });
  return data;
}

/** The owner's «замок» on one or several copies (no selling, no burning). */
export async function setCardsLocked(cardIds: number[], locked: boolean): Promise<{ card_ids: number[]; locked: boolean }> {
  const { data } = await api.patch<{ card_ids: number[]; locked: boolean }>("/collection/cards/lock", {
    card_ids: cardIds, locked,
  });
  return data;
}

export interface CardFilterOptions {
  countries: string[];
  clubs: string[];
}

export async function fetchCardFilterOptions(): Promise<CardFilterOptions> {
  const { data } = await api.get<CardFilterOptions>("/collection/filter-options");
  return data;
}

/** Saved default card filter (every field optional). */
export interface CardFilterDefault {
  rarity?: Rarity | null;
  country?: string | null;
  club?: string | null;
  position?: string | null;
  sort_by?: "rating" | "rarity" | "acquired_at" | null;
  has_skill?: boolean | null;
}

export async function fetchCardFilterDefault(): Promise<CardFilterDefault | null> {
  const { data } = await api.get<CardFilterDefault | null>("/collection/filter-default");
  return data;
}

export async function saveCardFilterDefault(filter: CardFilterDefault | null): Promise<CardFilterDefault | null> {
  const { data } = await api.put<CardFilterDefault | null>("/collection/filter-default", filter ?? {});
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

export async function feedDiamondCard(
  diamondCardId: number,
  materialCardIds: number[],
  confirmSkillLoss = false
): Promise<FeedCardsResult> {
  const { data } = await api.post<FeedCardsResult>("/collection/diamond-upgrade/feed", {
    diamond_card_id: diamondCardId,
    material_card_ids: materialCardIds,
    confirm_skill_loss: confirmSkillLoss,
  });
  return data;
}

export interface SellDuplicatesResult {
  sold_count: number;
  coins_earned: number;
  new_balance: number;
  by_rarity: Record<string, number>;
  preview: boolean;
  /** Every spare by rarity (diamond included) and what each group pays. */
  available_by_rarity?: Record<string, number>;
  available_coins_by_rarity?: Record<string, number>;
}

/** Sells every spare copy (one of each player is always kept; skilled,
 * in-squad, traded and diamond copies are never touched). preview=true only
 * counts them for the confirmation dialog. */
export async function sellDuplicates(preview: boolean, rarities?: Rarity[]): Promise<SellDuplicatesResult> {
  const { data } = await api.post<SellDuplicatesResult>("/collection/cards/sell-duplicates", { preview, rarities });
  return data;
}

export async function fetchCardStars(cardId: number): Promise<CardStarState> {
  const { data } = await api.get<CardStarState>(`/collection/cards/${cardId}/stars`);
  return data;
}

export async function feedCardStars(
  cardId: number,
  payload: { all_free?: boolean; material_card_ids?: number[]; confirm_skill_loss?: boolean; idempotency_key: string },
): Promise<CardStarOperation> {
  const { data } = await api.post<CardStarOperation>(`/collection/cards/${cardId}/stars/feed`, payload);
  return data;
}

export async function claimCardStar(cardId: number, idempotencyKey: string): Promise<CardStarOperation> {
  const { data } = await api.post<CardStarOperation>(`/collection/cards/${cardId}/stars/claim`, { idempotency_key: idempotencyKey });
  return data;
}
