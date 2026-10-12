import { api } from "@/lib/api";
import type { BlackjackAction, BlackjackStatus, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchBlackjackStatus(): Promise<BlackjackStatus> {
  const { data } = await api.get<BlackjackStatus>("/blackjack/status");
  return data;
}

export async function startBlackjack(): Promise<BlackjackAction> {
  const { data } = await api.post<BlackjackAction>("/blackjack/start");
  return data;
}

export async function blackjackHit(matchId: number): Promise<BlackjackAction> {
  const { data } = await api.post<BlackjackAction>(`/blackjack/matches/${matchId}/hit`);
  return data;
}

export async function blackjackStand(matchId: number): Promise<BlackjackAction> {
  const { data } = await api.post<BlackjackAction>(`/blackjack/matches/${matchId}/stand`);
  return data;
}

export async function createBlackjackStarsInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/blackjack/stars-invoice");
  return data;
}

export async function fetchBlackjackStarsInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/blackjack/stars-invoices/${payloadToken}`);
  return data;
}
