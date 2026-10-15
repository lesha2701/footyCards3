import { api } from "@/lib/api";
import type { PathCatalog, PathState, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchPathCatalog(): Promise<PathCatalog> {
  const { data } = await api.get<PathCatalog>("/path/catalog");
  return data;
}

export async function fetchPathState(cardId: number): Promise<PathState> {
  const { data } = await api.get<PathState>(`/path/cards/${cardId}`);
  return data;
}

export async function buyPathAttempt(cardId: number, idempotencyKey: string): Promise<PathState & { new_balance: number }> {
  const { data } = await api.post<PathState & { new_balance: number }>(`/path/cards/${cardId}/buy-attempt`, { idempotency_key: idempotencyKey });
  return data;
}

export async function createPathStarsInvoice(cardId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>(`/path/cards/${cardId}/stars-invoice`);
  return data;
}

export async function fetchPathStarsInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/path/stars-invoices/${payloadToken}`);
  return data;
}
