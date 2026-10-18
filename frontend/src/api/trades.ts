import { api } from "@/lib/api";
import type { TradeOffer } from "@/types";

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
