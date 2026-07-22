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

export async function acceptTradeOffer(id: number): Promise<TradeOffer> {
  const { data } = await api.post<TradeOffer>(`/trades/offers/${id}/accept`);
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
