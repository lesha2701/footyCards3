import { api } from "@/lib/api";
import type { Page, Player, TradeOffer, UserPublic } from "@/types";

export interface CreateTradePayload {
  receiver_id?: number;
  receiver_username?: string;
  offered_card_ids: number[];
  requested_card_ids: number[];
  sender_coins?: number;
  receiver_coins?: number;
  message?: string;
}

/** Anti-farming rules as they apply to the current player (backend trade_guard_service). */
export interface TradeRules {
  can_give: boolean;
  give_block_reason: string | null;
  min_account_age_days: number;
  min_active_days: number;
  daily_coins_receive_cap: number;
  coins_received_today: number;
  coin_tax_pct: number;
  coins_enabled: boolean;
  cards_both_sides: boolean;
}

export async function fetchTradeRules(): Promise<TradeRules> {
  const { data } = await api.get<TradeRules>("/trades/rules");
  return data;
}

// --- «Поиск обменов» (backend trade_finder_service) ---
export type TradeWishKind = "want" | "give";

export interface TradeWishes {
  wants: Player[];
  gives: Player[];
  max_wants: number;
  max_gives: number;
}

export interface TradeMatchCard {
  card_id: number;
  player: Player;
  marked_to_give: boolean;
}

export interface TradeMatch {
  user: UserPublic;
  mutual: boolean;
  they_have: TradeMatchCard[];
  they_want: TradeMatchCard[];
}

export async function fetchTradeWishes(): Promise<TradeWishes> {
  const { data } = await api.get<TradeWishes>("/trades/finder/wishes");
  return data;
}

export async function addTradeWish(kind: TradeWishKind, playerId: number): Promise<TradeWishes> {
  const { data } = await api.put<TradeWishes>("/trades/finder/wishes", { kind, player_id: playerId });
  return data;
}

export async function removeTradeWish(kind: TradeWishKind, playerId: number): Promise<TradeWishes> {
  const { data } = await api.delete<TradeWishes>(`/trades/finder/wishes/${kind}/${playerId}`);
  return data;
}

export async function fetchTradeMatches(): Promise<TradeMatch[]> {
  const { data } = await api.get<TradeMatch[]>("/trades/finder/matches");
  return data;
}

export async function searchPlayers(search: string): Promise<Player[]> {
  const { data } = await api.get<Page<Player>>("/players", { params: { search, page_size: 30 } });
  return data.items;
}

export async function fetchTradeOffers(params: { status?: string; direction?: "incoming" | "outgoing" } = {}): Promise<TradeOffer[]> {
  const { data } = await api.get<TradeOffer[]>("/trades/offers", { params });
  return data;
}

export async function fetchTradeOffer(id: number): Promise<TradeOffer> {
  const { data } = await api.get<TradeOffer>(`/trades/offers/${id}`);
  return data;
}

export async function createTradeOffer(payload: CreateTradePayload): Promise<TradeOffer> {
  const { data } = await api.post<TradeOffer>("/trades/offers", payload);
  return data;
}

export async function acceptTradeOffer(id: number): Promise<TradeOffer & { new_balance: number }> {
  const { data } = await api.post<TradeOffer & { new_balance: number }>(`/trades/offers/${id}/accept`);
  return data;
}

export async function rejectTradeOffer(id: number): Promise<TradeOffer> {
  const { data } = await api.post<TradeOffer>(`/trades/offers/${id}/reject`);
  return data;
}

export async function cancelTradeOffer(id: number): Promise<TradeOffer> {
  const { data } = await api.post<TradeOffer>(`/trades/offers/${id}/cancel`);
  return data;
}
